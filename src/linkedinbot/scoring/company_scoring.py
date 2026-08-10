"""Company Quality Scoring - PRD Section 12.1/12.3, TDD v1.1 Fix 3
(Roadmap M7.1).

**`CompanyScore` (yeni domain kavramı):** `ports/company_repository_port.py`'nin
kendi modul dokumani zaten acikca belirtir: "CompanyProfile'in ... Company
Quality Score, Score Breakdown ... `company_scores`'a (M7.1, HENUZ DOMAIN
MODELI YOK) tasindigini belirtir." Bu modul o notu yerine getirir.
`CompanyScore`'un alan sekli, `db/models.py`'nin ZATEN ONAYLANMIS
`CompanyScoreOrm`'siyle (M1.2) BIREBIR eslesir (`weight_profile_id: UUID |
None`, `rubric_version: int`, `score_total: float | None`,
`score_breakdown: dict`, `evaluated_at: datetime`) - gercek kalicilik
(DB'ye yazma/okuma) henuz insa edilmemis bir orkestratorun (M9) isidir;
Roadmap M7.1'in kendi bagimliligi M1.2 (DB) DEGIL, M1.3'tur (Portlar) -
bu yuzden bu modul hicbir repository/DB'ye erismez, SAF bir fonksiyondur
(`history/diff_engine.py`, M4.2 ile ayni desen).

**"LLM sinyal cikarir, kod skoru hesaplar" (TDD Section 10):**
`config/prompts/company_scoring.prompt.md` (M5.2, degistirilmemis) LLM'den
ALTI boyutun HER BIRI icin ayri ayri bir degerlendirme ister ve acikca
"Do not combine the dimensions into a single overall score" der. Bu
modul, `CompanyScoringInference` yapisal cikti semasini tanimlar (6 boyut,
her biri bir `DimensionAssessment` = sayisal skor [0-100, "insufficient
information" ise None] + gerekce) ve AGIRLIKLI TOPLAMI (Section 12.1'in
`CompanyQualityWeights`'i, M2.1, degistirilmemis) DETERMINISTIK olarak
KOD ICINDE hesaplar - LLM'den hicbir zaman dogrudan "0-100 nihai skor"
istenmez.

**Boyut-bazli "insufficient information" -> yeniden normalizasyon (PRD
12.3'un genel ilkesinin, Section 13.1'deki 5 AI Match bileseniyle AYNI
YAPIDA, burada 6 sirket boyutuna uygulanmasi):** PRD 12.3, Section 13.1
duzeyinde "bir bilesen hesaplamadan cikarilir, kalan bileslerin
agirliklari kendi aralarinda orantili olarak yeniden normalize edilir
(sifir/notr varsayilmaz)" ilkesini acikca tanimlar. Roadmap M7.1'in kendi
"Amac"i ("Unrated yeniden normalizasyonunu... uygulamak") ve "Tamamlanma
Dogrulamasi"i ("Unrated senaryosunda agirlik matematigi elle
hesaplananla eslesir") bu AYNI ilkenin BURADA, sirket puanlamasinin
KENDI ALTI boyutuna (Section 13.1'in 5 bilesenine degil) uygulanmasini
gerektirir - sablonun kendi "explicitly note if there is insufficient
information to assess THAT DIMENSION" (boyut-bazli, sirket-capinda
degil) talimatiyla dogrudan tutarlidir. Agirlikli toplam bu yuzden
YALNIZCA derecelendirilmis (score is not None) boyutlar uzerinden,
KALAN agirliklarin toplamina bolunerek hesaplanir. HICBIR boyut
derecelendirilemezse (`score` hepsi None) skor "Unrated" (`score_total =
None`) olarak isaretlenir - PRD 12.3'un "yeterli veri bulunamiyorsa...
Unrated" tanimiyla tutarlidir.

**Gateway basarisiz olursa (None doner - repair de basarisiz oldu):**
M6.3/M6.4'un "asla uydurma bir skor uretme" ilkesiyle tutarli olarak,
`score_total=None` (Unrated) ve bos bir `score_breakdown` ile sonuclanir.

**Kapsam disi (Roadmap M7.1'in kendi "Amac"inda ADI GECMEZ, sonraki
milestone'larin isidir):** Company Quality Score esiginin (varsayilan 50)
UYGULANMASI/dislama karari (Section 12.3'un ilk maddesi, muhtemelen
orkestrasyon/raporlama asamasi), skor bantlari (Section 12.2, raporlama),
30 gunluk "Last Evaluated Timestamp" tazelik penceresi (Section 12.4 -
Roadmap M7.1'in kendi Tamamlanma Dogrulamasi YALNIZCA rubric_version
tabanli 3-parcali anahtari test eder, zaman-bazli gecerlilik penceresini
DEGIL).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from linkedinbot.adapters.llm.gateway import LLMGateway
from linkedinbot.config.schema import CompanyQualityWeights
from linkedinbot.scoring.score_cache import get_cached_score

_DIMENSIONS = (
    "brand_reputation_prestige",
    "company_scale",
    "career_development_training_culture",
    "sector_position",
    "corporate_stability",
    "external_signals",
)


class DimensionAssessment(BaseModel):
    score: float | None = Field(default=None, ge=0.0, le=100.0)
    justification: str


class CompanyScoringInference(BaseModel):
    brand_reputation_prestige: DimensionAssessment
    company_scale: DimensionAssessment
    career_development_training_culture: DimensionAssessment
    sector_position: DimensionAssessment
    corporate_stability: DimensionAssessment
    external_signals: DimensionAssessment


class CompanyScore(BaseModel):
    company_id: str
    weight_profile_id: UUID | None
    rubric_version: int
    score_total: float | None = Field(default=None, ge=0.0, le=100.0)
    score_breakdown: dict[str, float | None]
    evaluated_at: datetime


def _weighted_score(
    inference: CompanyScoringInference, weights: CompanyQualityWeights
) -> float | None:
    rated_weight_sum = 0.0
    weighted_total = 0.0
    for dimension in _DIMENSIONS:
        score = getattr(inference, dimension).score
        if score is None:
            continue
        weight = getattr(weights, dimension)
        rated_weight_sum += weight
        weighted_total += score * weight

    if rated_weight_sum == 0.0:
        return None
    return weighted_total / rated_weight_sum


def score_company(
    company_id: str,
    company_context: str,
    weights: CompanyQualityWeights,
    weight_profile_id: UUID | None,
    rubric_version: int,
    cached_scores: dict[tuple[str, UUID | None, int], CompanyScore],
    llm_gateway: LLMGateway,
    model: str,
    evaluated_at: datetime,
) -> CompanyScore:
    cached = get_cached_score(cached_scores, company_id, weight_profile_id, rubric_version)
    if cached is not None:
        return cached

    inference = llm_gateway.generate(
        "company_scoring",
        CompanyScoringInference,
        model,
        company_name=company_id,
        company_context=company_context,
    )

    if inference is None:
        return CompanyScore(
            company_id=company_id,
            weight_profile_id=weight_profile_id,
            rubric_version=rubric_version,
            score_total=None,
            score_breakdown={},
            evaluated_at=evaluated_at,
        )

    score_breakdown = {
        dimension: getattr(inference, dimension).score for dimension in _DIMENSIONS
    }
    return CompanyScore(
        company_id=company_id,
        weight_profile_id=weight_profile_id,
        rubric_version=rubric_version,
        score_total=_weighted_score(inference, weights),
        score_breakdown=score_breakdown,
        evaluated_at=evaluated_at,
    )
