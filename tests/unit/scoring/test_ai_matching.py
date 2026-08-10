"""scoring/ai_matching.py icin birim testleri (Roadmap M7.2, PRD Section
13, FR-7, FR-18, RISK-10).

Roadmap M7.2 "Tamamlanma Dogrulamasi": "Sahte LLM sinyalleriyle birim
testi - agirlikli toplam formulu elle hesaplanan beklenen skorla birebir
eslesir; gerekce maddelerinin yalnizca sinyal setindeki alanlara atifta
bulundugu dogrulanir; ayni girdi iki kez calistirilir, ikinci seferde LLM
cagrisi yapilmadigi (cache hit) dogrulanir."

Proje talimatiyla acikca onaylanan mimari kararlar (bkz. modul dokumani):
- "Career Goal Alignment" icin eksik olan `career_goal_alignment.prompt.md`
  (M5.2'nin kendi 4 sablonu arasinda YOKTU) kullanicinin acik kararıyla
  M7.2'nin bir PARCASI olarak eklendi - Section 13.1'in 5. bileseninin
  hicbir onceki milestone'da hesaplanan bir kaynagi olmadigi icin.
- Department/Experience/Location sinyalleri, M6.5'in `PipelineResult`'i
  DEGIL, dogrudan (zaten hesaplanmis) DUZ degerler olarak alinir -
  `filtering.pipeline`'a (dict-anahtarli, string-bagimli bir yapi) COUPLE
  OLMAMAK icin; cagiran (henuz insa edilmemis bir orkestrator, M9) bu
  degerleri M6.5'in ciktisindan cikarmaktan sorumludur.
- LLM Gateway sahte (fake) bir nesneyle test edilir - gercek Anthropic
  API'ye HICBIR ZAMAN dokunulmaz.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from linkedinbot.config.schema import AIMatchWeights
from linkedinbot.domain.evaluated_job import MatchRationaleItem
from linkedinbot.scoring.ai_matching import (
    AIMatchRationaleInference,
    AIMatchResult,
    CareerGoalAlignmentInference,
    score_ai_match,
)
from linkedinbot.scoring.company_scoring import CompanyScore

EVALUATED_AT = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
TEST_MODEL = "claude-3-5-haiku-20241022"

# PRD Section 13.1'in kendi varsayilan agirliklari (toplam 1.0).
WEIGHTS = AIMatchWeights(
    department_role_relevance=0.35,
    experience_level_fit=0.15,
    location_fit=0.10,
    company_quality_contribution=0.25,
    career_goal_alignment=0.15,
)

_VALID_RATIONALE = AIMatchRationaleInference(
    items=[
        MatchRationaleItem(
            component="Department/Role Relevance",
            value="0.90",
            explanation="Strong department match.",
        ),
        MatchRationaleItem(
            component="Experience Level Fit", value="Yes", explanation="Matches Entry Level."
        ),
        MatchRationaleItem(
            component="Location Fit", value="Yes", explanation="Located in Istanbul."
        ),
    ]
)


def _company_score(**overrides) -> CompanyScore:
    data = {
        "company_id": "Acme Corp",
        "weight_profile_id": None,
        "rubric_version": 1,
        "score_total": 80.0,
        "score_breakdown": {},
        "evaluated_at": EVALUATED_AT,
    }
    data.update(overrides)
    return CompanyScore(**data)


class _FakeLLMGateway:
    """Sablon adina gore (career_goal_alignment / ai_match_rationale) sabit
    bir yanit donen sahte Gateway - M6.4/M7.1'in tekli-sonuc sahte deseniyle
    AYNI, ama IKI FARKLI sablon icin ayri yanit tablosu tasir."""

    def __init__(self, alignment_result=None, rationale_result=None):
        self._alignment_result = alignment_result
        self._rationale_result = rationale_result
        self.calls: list[dict] = []

    def generate(self, template_name, response_model, model, **template_variables):
        self.calls.append(
            {
                "template_name": template_name,
                "response_model": response_model,
                "model": model,
                **template_variables,
            }
        )
        if template_name == "career_goal_alignment":
            return self._alignment_result
        if template_name == "ai_match_rationale":
            return self._rationale_result
        raise AssertionError(f"unexpected template_name: {template_name}")


def _score(llm_gateway, cache=None, **overrides):
    kwargs = {
        "job_id": "https://www.linkedin.com/jobs/view/1",
        "account_id": uuid4(),
        "config_version": 1,
        "job_title": "Sales Executive",
        "job_description": "Managing key accounts.",
        "career_goals": "Build a career in sales and business development.",
        "department_relevance_confidence": 0.9,
        "experience_level_fit": True,
        "location_fit": True,
        "company_score": _company_score(),
        "weights": WEIGHTS,
        "cached_results": cache if cache is not None else {},
        "llm_gateway": llm_gateway,
        "model": TEST_MODEL,
        "evaluated_at": EVALUATED_AT,
    }
    kwargs.update(overrides)
    return score_ai_match(**kwargs)


def test_weighted_score_matches_manual_calculation_with_all_five_components():
    # dept: 0.9*100*.35=31.5; experience: 100*.15=15; location: 100*.10=10;
    # company: 80*.25=20; career: 0.8*100*.15=12. Total = 88.5.
    llm_gateway = _FakeLLMGateway(
        alignment_result=CareerGoalAlignmentInference(score=0.8, explanation="Good fit."),
        rationale_result=_VALID_RATIONALE,
    )

    result = _score(llm_gateway)

    assert result.ai_match_score == 88.5


def test_company_quality_unrated_excludes_and_renormalizes_remaining_components():
    # Unrated -> company_quality_contribution (.25) haric tutulur; kalan
    # agirlik toplami .35+.15+.10+.15=.75.
    # dept: 0.9*100*.35=31.5; experience: 100*.15=15; location: 100*.10=10;
    # career: 0.8*100*.15=12. Toplam = 68.5 / 0.75.
    llm_gateway = _FakeLLMGateway(
        alignment_result=CareerGoalAlignmentInference(score=0.8, explanation="Good fit."),
        rationale_result=_VALID_RATIONALE,
    )

    result = _score(llm_gateway, company_score=_company_score(score_total=None))

    assert result.ai_match_score == (31.5 + 15 + 10 + 12) / 0.75


def test_result_carries_at_least_three_grounded_rationale_items():
    llm_gateway = _FakeLLMGateway(
        alignment_result=CareerGoalAlignmentInference(score=0.8, explanation="Good fit."),
        rationale_result=_VALID_RATIONALE,
    )

    result = _score(llm_gateway)

    assert len(result.match_rationale) >= 3
    expected_components = {
        "department/role relevance",
        "experience level fit",
        "location fit",
        "company quality",
        "career goal alignment",
    }
    for item in result.match_rationale:
        assert item.component.strip().lower() in expected_components


def test_rationale_item_referencing_an_unknown_component_is_ungrounded_and_score_unavailable():
    # RISK-10: sinyal setinde karsiligi olmayan bir madde -> "Scoring
    # Unavailable" (skor UYDURULMAZ, tahmin yerine None).
    ungrounded_rationale = AIMatchRationaleInference(
        items=[
            MatchRationaleItem(
                component="Salary Expectations", value="High", explanation="Made up."
            ),
            MatchRationaleItem(
                component="Experience Level Fit", value="Yes", explanation="Matches."
            ),
            MatchRationaleItem(component="Location Fit", value="Yes", explanation="Matches."),
        ]
    )
    llm_gateway = _FakeLLMGateway(
        alignment_result=CareerGoalAlignmentInference(score=0.8, explanation="Good fit."),
        rationale_result=ungrounded_rationale,
    )

    result = _score(llm_gateway)

    assert result.ai_match_score is None
    assert result.match_rationale is None


def test_unavailable_career_goal_alignment_inference_results_in_scoring_unavailable():
    llm_gateway = _FakeLLMGateway(alignment_result=None, rationale_result=_VALID_RATIONALE)

    result = _score(llm_gateway)

    assert result.ai_match_score is None
    assert result.match_rationale is None
    # Gerekce olusturma cagrisina hic gerek yok - hesaplanacak bir skor yok.
    assert all(call["template_name"] != "ai_match_rationale" for call in llm_gateway.calls)


def test_unavailable_rationale_inference_results_in_scoring_unavailable():
    # FR-7: skor gerekcesiz sunulmaz - gerekce uretilemezse skor de
    # UYDURULMAZ, hesaplanmis olsa bile None'a donusturulur.
    llm_gateway = _FakeLLMGateway(
        alignment_result=CareerGoalAlignmentInference(score=0.8, explanation="Good fit."),
        rationale_result=None,
    )

    result = _score(llm_gateway)

    assert result.ai_match_score is None
    assert result.match_rationale is None


def test_cache_hit_returns_cached_result_without_calling_the_llm_gateway_again():
    llm_gateway = _FakeLLMGateway(
        alignment_result=CareerGoalAlignmentInference(score=0.8, explanation="Good fit."),
        rationale_result=_VALID_RATIONALE,
    )
    cache: dict = {}

    first = _score(llm_gateway, cache=cache)
    cache[(first.job_id, first.account_id, first.config_version)] = first

    second = _score(
        llm_gateway,
        cache=cache,
        job_id=first.job_id,
        account_id=first.account_id,
        config_version=first.config_version,
    )

    assert second == first
    assert len(llm_gateway.calls) == 2  # yalnizca ILK cagridan (alignment + rationale)


def test_cache_miss_when_config_version_changes_calls_llm_gateway_again():
    llm_gateway = _FakeLLMGateway(
        alignment_result=CareerGoalAlignmentInference(score=0.8, explanation="Good fit."),
        rationale_result=_VALID_RATIONALE,
    )
    cache: dict = {}
    job_id = "https://www.linkedin.com/jobs/view/1"
    account_id = uuid4()

    first = _score(llm_gateway, cache=cache, job_id=job_id, account_id=account_id, config_version=1)
    cache[(job_id, account_id, 1)] = first

    _score(llm_gateway, cache=cache, job_id=job_id, account_id=account_id, config_version=2)

    assert len(llm_gateway.calls) == 4  # iki AYRI config_version -> iki tam cagri seti


def test_renders_the_career_goal_alignment_template_with_the_given_details():
    llm_gateway = _FakeLLMGateway(
        alignment_result=CareerGoalAlignmentInference(score=0.8, explanation="Good fit."),
        rationale_result=_VALID_RATIONALE,
    )

    _score(
        llm_gateway,
        job_title="Sales Executive",
        job_description="Managing key accounts.",
        career_goals="Build a career in sales.",
    )

    alignment_calls = [
        c for c in llm_gateway.calls if c["template_name"] == "career_goal_alignment"
    ]
    assert len(alignment_calls) == 1
    call = alignment_calls[0]
    assert call["response_model"] is CareerGoalAlignmentInference
    assert call["model"] == TEST_MODEL
    assert call["career_goals"] == "Build a career in sales."
    assert call["job_title"] == "Sales Executive"
    assert call["job_description"] == "Managing key accounts."


def test_renders_the_ai_match_rationale_template_with_computed_signals_only():
    # Grounding (TDD Section 10): rationale prompt'una HAM is ilani metni
    # degil, yalnizca hesaplanmis sinyaller/notlar verilir.
    llm_gateway = _FakeLLMGateway(
        alignment_result=CareerGoalAlignmentInference(score=0.8, explanation="Strong fit."),
        rationale_result=_VALID_RATIONALE,
    )

    _score(llm_gateway, company_score=_company_score(score_total=80.0))

    rationale_calls = [c for c in llm_gateway.calls if c["template_name"] == "ai_match_rationale"]
    assert len(rationale_calls) == 1
    call = rationale_calls[0]
    assert call["response_model"] is AIMatchRationaleInference
    assert "job_title" not in call
    assert "job_description" not in call
    assert call["company_quality_score"] == "80.0"
    assert call["career_goal_alignment_score"] == "0.8"
    assert call["career_goal_alignment_note"] == "Strong fit."


def test_department_relevance_note_does_not_claim_a_match_it_cannot_verify():
    # Self-review kaygisi: `department_relevance_note`, department esik
    # degerini (config'ten, varsayilan 0.65 - PRD Section 17) HIC ALMAYAN
    # bu fonksiyonun kendi icinde SABIT KODLANMIS bir "0.5" kesimiyle
    # "Matches an accepted department." ifadesini KULLANMAMALIDIR - bu,
    # PRD/TDD'de hicbir yerde tanimlanmayan, UYDURULMUS bir esiktir ve
    # gercek (cagirana ozgu) esigin ALTINDA kalan bir guven degeri icin
    # bile yanlislikla "eslesme" iddia edebilirdi. Not, yalnizca HAM
    # sayisal degeri tarafsizca yansitmalidir.
    llm_gateway = _FakeLLMGateway(
        alignment_result=CareerGoalAlignmentInference(score=0.8, explanation="Good fit."),
        rationale_result=_VALID_RATIONALE,
    )

    _score(llm_gateway, department_relevance_confidence=0.55)

    rationale_calls = [c for c in llm_gateway.calls if c["template_name"] == "ai_match_rationale"]
    note = rationale_calls[0]["department_relevance_note"]
    assert "matches an accepted department" not in note.lower()
    assert "0.55" in note


def test_result_type_alone_carries_the_given_cache_key_components():
    llm_gateway = _FakeLLMGateway(
        alignment_result=CareerGoalAlignmentInference(score=0.8, explanation="Good fit."),
        rationale_result=_VALID_RATIONALE,
    )
    account_id = uuid4()

    result: AIMatchResult = _score(
        llm_gateway, job_id="job-42", account_id=account_id, config_version=7
    )

    assert result.job_id == "job-42"
    assert result.account_id == account_id
    assert result.config_version == 7
    assert result.evaluated_at == EVALUATED_AT
