"""AI Match Scoring - PRD Section 13, FR-7, FR-18, RISK-10, TDD Section 10
(Roadmap M7.2).

**"LLM sinyal cikarir, kod skoru hesaplar":** Section 13.1'in 5 bileseni
icin LLM'den DOGRUDAN "0-100 nihai skor" istenmez. Dort bilesenin sinyali
BASKA yerlerde ZATEN hesaplanmistir ve bu modul BUNLARI DUZ deger olarak
alir - YENIDEN HESAPLAMAZ:
- Department/Role Relevance: M6.4'un `filter_by_department()` guveni.
- Experience Level Fit / Location Fit: M6.3/M6.2'nin `FilterResult.passed`
  boolean'lari (bu asamaya ulasan bir ilan zaten bu filtrelerden gecmistir
  - bkz. M6.5).
- Company Quality Contribution: M7.1'in `CompanyScore.score_total`'i.

Bu deger BASKA yerlerin ciktisi oldugu icin, bu modul KASITLI OLARAK
`filtering.pipeline.PipelineResult`'i (string-anahtarli bir dict tasiyan
bir tip) ICE AKTARMAZ - cagiran (henuz insa edilmemis bir orkestrator,
M9), bu degerleri M6.5'in ciktisindan cikarmaktan sorumludur; bu modul
yalnizca DUZ, tipli degerler alir (`filtering`e HICBIR bagimliligi yoktur).

**Career Goal Alignment - eksik sinyal kaynagi (proje talimatiyla acikca
onaylanan mimari karar):** Section 13.1'in 5. bileseni olan Career Goal
Alignment'in, M6.1-M6.5/M7.1'in HICBIRINDE onceden hesaplanmis bir kaynagi
YOKTUR - TDD Section 10'un kendi ornek listesi bunu ACIKCA bir LLM
sinyali olarak sayar ("career goal alignment: 0.0-1.0 + kisa aciklama").
Ancak M5.2'nin ZATEN onaylanmis dort sablonu (department_matching,
experience_inference, company_scoring, ai_match_rationale) bunun icin
BIR TANESINI DAHI icermez - ve `ai_match_rationale.prompt.md`'nin KENDI
degisken listesi (`${career_goal_alignment_score}`,
`${career_goal_alignment_note}`) bu sinyalin rationale cagrisindan ONCE
ZATEN hesaplanmis olmasini ACIKCA VARSAYAR. Kullanicinin acik kararıyla,
`config/prompts/career_goal_alignment.prompt.md` M7.2'nin bir PARCASI
olarak eklendi (M5.2'nin ayni mimarisiyle: PromptRegistry uzerinden
yuklenir, Python icine hicbir prompt metni gomulmez, yapisal LLM ciktisi).

**Grounding (RISK-10 mitigasyonu, TDD Section 10):** `ai_match_rationale`
cagrisina HAM is ilani metni (`job_title`/`job_description`) VERILMEZ -
yalnizca hesaplanmis sinyaller ve onlarin kisa notlari. Donen gerekce
maddeleri, SABIT bes bilesen etiketinden (Department/Role Relevance,
Experience Level Fit, Location Fit, Company Quality, Career Goal
Alignment - `ai_match_rationale.prompt.md`'nin kendi "component" alani
icin verdigi ayni ornek etiketler) BIRINE (buyuk/kucuk harf duyarsiz)
karsilik gelmelidir; aksi halde "sinyal setinde karsiligi olmayan bir
madde" (TDD Section 10) sayilir. M5.3'un Gateway'i yalnizca SEMA
duzeyinde (Pydantic ValidationError) bir repair denemesi yapar - bu
EK, anlamsal (grounding) kontrol M5.3'u YENIDEN TASARLAMAZ; sema
gecerli ama anlamsal olarak gerceksiz bir yanit, AYRI bir ikinci repair
denemesi OLMADAN dogrudan "Scoring Unavailable" sayilir (M6.3/M6.4/
M7.1'in "asla uydurma bir skor uretme" ilkesiyle tutarli).

**FR-7 (skor gerekcesiz sunulmaz):** Gerekce uretilemez veya
gerceksizse (ungrounded), ONCEDEN hesaplanmis agirlikli skor da
ATILIR - `ai_match_score` ve `match_rationale` HER ZAMAN birlikte var
olur veya birlikte None'dur (`EvaluatedJob`'un M1.1'de zaten kurdugu
ayni kurala, `AIMatchResult` uzerinde BAGIMSIZ olarak uygulanir - tum
`EvaluatedJob` alanlarini tasimayan, kucuk, kapsamli bir sonuc tipi
oldugu icin `EvaluatedJob`'un kendisi yeniden kullanilmaz, M7.1'in
`CompanyScore`'u yeniden kullanmama gerekcesiyle AYNI).

**FR-18 (Job-seviyesi onbellek anahtari):** `Job ID + Account ID +
Config Version` uclusu. Bu modul SAF'tir (M7.1'in `score_cache.py`
deseniyle AYNI): hicbir depoya erismez, cagiran "onbellek" dict'ini
acikca verir ve gunceller.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from linkedinbot.adapters.llm.gateway import LLMGateway
from linkedinbot.config.schema import AIMatchWeights
from linkedinbot.domain.evaluated_job import MatchRationaleItem
from linkedinbot.scoring.company_scoring import CompanyScore

_VALID_COMPONENT_NAMES = frozenset(
    {
        "department/role relevance",
        "experience level fit",
        "location fit",
        "company quality",
        "career goal alignment",
    }
)


class CareerGoalAlignmentInference(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    explanation: str


class AIMatchRationaleInference(BaseModel):
    items: list[MatchRationaleItem] = Field(min_length=3)


class AIMatchResult(BaseModel):
    job_id: str
    account_id: UUID
    config_version: int
    ai_match_score: float | None = Field(default=None, ge=0.0, le=100.0)
    match_rationale: list[MatchRationaleItem] | None = None
    evaluated_at: datetime

    @model_validator(mode="after")
    def _score_and_rationale_travel_together(self) -> AIMatchResult:
        has_score = self.ai_match_score is not None
        has_rationale = bool(self.match_rationale)
        if has_score != has_rationale:
            raise ValueError(
                "ai_match_score ve match_rationale FR-7 geregi birlikte "
                "bulunur veya birlikte bulunmaz (skor gerekcesiz sunulmaz)."
            )
        return self


def _is_grounded(rationale: AIMatchRationaleInference) -> bool:
    return all(
        item.component.strip().lower() in _VALID_COMPONENT_NAMES for item in rationale.items
    )


def _weighted_ai_match_score(
    department_relevance_confidence: float,
    experience_level_fit: bool,
    location_fit: bool,
    company_quality_score: float | None,
    career_goal_alignment_score: float,
    weights: AIMatchWeights,
) -> float | None:
    components = [
        (department_relevance_confidence * 100.0, weights.department_role_relevance),
        (100.0 if experience_level_fit else 0.0, weights.experience_level_fit),
        (100.0 if location_fit else 0.0, weights.location_fit),
        (career_goal_alignment_score * 100.0, weights.career_goal_alignment),
    ]
    if company_quality_score is not None:
        components.append((company_quality_score, weights.company_quality_contribution))

    total_weight = sum(weight for _, weight in components)
    if total_weight == 0.0:
        # M7.1's _weighted_score() ile ayni koruma: butun agirlik Unrated
        # olarak haric tutulan tek bilesen uzerindeyse, bir skor UYDURULMAZ.
        return None
    weighted_total = sum(value * weight for value, weight in components)
    return weighted_total / total_weight


def score_ai_match(
    job_id: str,
    account_id: UUID,
    config_version: int,
    job_title: str,
    job_description: str,
    career_goals: str,
    department_relevance_confidence: float,
    experience_level_fit: bool,
    location_fit: bool,
    company_score: CompanyScore,
    weights: AIMatchWeights,
    cached_results: dict[tuple[str, UUID, int], AIMatchResult],
    llm_gateway: LLMGateway,
    model: str,
    evaluated_at: datetime,
) -> AIMatchResult:
    cached = cached_results.get((job_id, account_id, config_version))
    if cached is not None:
        return cached

    def _unavailable() -> AIMatchResult:
        return AIMatchResult(
            job_id=job_id,
            account_id=account_id,
            config_version=config_version,
            evaluated_at=evaluated_at,
        )

    alignment = llm_gateway.generate(
        "career_goal_alignment",
        CareerGoalAlignmentInference,
        model,
        career_goals=career_goals,
        job_title=job_title,
        job_description=job_description,
    )
    if alignment is None:
        return _unavailable()

    ai_match_score = _weighted_ai_match_score(
        department_relevance_confidence,
        experience_level_fit,
        location_fit,
        company_score.score_total,
        alignment.score,
        weights,
    )
    if ai_match_score is None:
        return _unavailable()

    rationale = llm_gateway.generate(
        "ai_match_rationale",
        AIMatchRationaleInference,
        model,
        department_relevance_score=str(department_relevance_confidence),
        department_relevance_note=(
            f"Department relevance confidence: {department_relevance_confidence:.2f}."
        ),
        experience_level_fit_note=(
            "Matches an accepted experience level."
            if experience_level_fit
            else "Does not match an accepted experience level."
        ),
        location_fit_note=(
            "Located in a target location."
            if location_fit
            else "Not located in a target location."
        ),
        company_quality_score=(
            str(company_score.score_total) if company_score.score_total is not None else "Unrated"
        ),
        career_goal_alignment_score=str(alignment.score),
        career_goal_alignment_note=alignment.explanation,
    )
    if rationale is None or not _is_grounded(rationale):
        return _unavailable()

    return AIMatchResult(
        job_id=job_id,
        account_id=account_id,
        config_version=config_version,
        ai_match_score=ai_match_score,
        match_rationale=rationale.items,
        evaluated_at=evaluated_at,
    )
