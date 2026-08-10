"""scoring/company_scoring.py icin birim testleri (Roadmap M7.1, PRD
Section 12.1/12.3/12.4).

Roadmap M7.1 "Tamamlanma Dogrulamasi": "Birim testleri - ayni agirlik/
rubric_version ile iki cagri -> ikincisi cache hit (LLM mock'unun bir kez
cagrildigi dogrulanir); rubric_version degisince cache miss; Unrated
senaryosunda agirlik matematigi elle hesaplananla eslesir."

Proje talimatiyla acikca onaylanan mimari kararlar (bkz. modul dokumani):
- `score_company()` SAF bir fonksiyondur - `cached_scores` dict'ini
  MUTATE ETMEZ; ikinci cagridan once onbellege eklemek cagiranin
  sorumlulugudur (diff_engine.py'nin M4.2'deki iki-calistirma deseniyle
  AYNI).
- LLM'in "insufficient information" (M5.2'nin zaten onayli
  company_scoring.prompt.md'sinin kendi ifadesi) BOYUT-BAZLI raporlamasi,
  o boyutu `score=None` ile temsil eder; agirlikli toplam yalnizca
  DERECELENDIRILMIS (score is not None) boyutlar uzerinden, KALAN
  agirliklarin kendi aralarinda orantili yeniden normalizasyonuyla
  hesaplanir (PRD 12.3'un genel "sifir/notr varsayma, orantili yeniden
  normalize et" ilkesinin, Section 13.1'deki AYNI ilkeyle YAPISAL OLARAK
  ozdes bir uygulamasi - burada 5 AI Match bileseni yerine 6 sirket
  boyutuna uygulanir). HICBIR boyut derecelendirilemezse skor "Unrated"
  (None) olarak isaretlenir.

Gercek Anthropic API'ye HICBIR ZAMAN dokunulmaz.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from linkedinbot.config.schema import CompanyQualityWeights
from linkedinbot.scoring.company_scoring import (
    CompanyScoringInference,
    DimensionAssessment,
    score_company,
)

EVALUATED_AT = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
TEST_MODEL = "claude-3-5-haiku-20241022"

# PRD Section 12.1'in kendi varsayilan agirliklari (toplam 1.0).
WEIGHTS = CompanyQualityWeights(
    brand_reputation_prestige=0.25,
    company_scale=0.20,
    career_development_training_culture=0.20,
    sector_position=0.15,
    corporate_stability=0.10,
    external_signals=0.10,
)


def _assessment(score: float | None, justification: str = "...") -> DimensionAssessment:
    return DimensionAssessment(score=score, justification=justification)


def _fully_rated_inference() -> CompanyScoringInference:
    return CompanyScoringInference(
        brand_reputation_prestige=_assessment(80.0),
        company_scale=_assessment(70.0),
        career_development_training_culture=_assessment(90.0),
        sector_position=_assessment(60.0),
        corporate_stability=_assessment(100.0),
        external_signals=_assessment(50.0),
    )


class _FakeLLMGateway:
    def __init__(self, result):
        self._result = result
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
        return self._result


def test_cache_hit_returns_cached_score_and_does_not_call_the_llm_gateway():
    llm_gateway = _FakeLLMGateway(result=_fully_rated_inference())
    cache: dict = {}

    first = score_company(
        "Acme Corp", "Founded 1998.", WEIGHTS, None, 1, cache, llm_gateway, TEST_MODEL, EVALUATED_AT
    )
    cache[("Acme Corp", None, 1)] = first

    second = score_company(
        "Acme Corp", "Founded 1998.", WEIGHTS, None, 1, cache, llm_gateway, TEST_MODEL, EVALUATED_AT
    )

    assert second == first
    assert len(llm_gateway.calls) == 1


def test_cache_miss_when_rubric_version_changes_calls_llm_gateway_again():
    llm_gateway = _FakeLLMGateway(result=_fully_rated_inference())
    cache: dict = {}

    first = score_company(
        "Acme Corp", "Founded 1998.", WEIGHTS, None, 1, cache, llm_gateway, TEST_MODEL, EVALUATED_AT
    )
    cache[("Acme Corp", None, 1)] = first

    score_company(
        "Acme Corp", "Founded 1998.", WEIGHTS, None, 2, cache, llm_gateway, TEST_MODEL, EVALUATED_AT
    )

    assert len(llm_gateway.calls) == 2


def test_weighted_score_matches_manual_calculation_when_all_dimensions_rated():
    # 80*.25 + 70*.20 + 90*.20 + 60*.15 + 100*.10 + 50*.10 = 76.0
    llm_gateway = _FakeLLMGateway(result=_fully_rated_inference())

    result = score_company(
        "Acme Corp", "Founded 1998.", WEIGHTS, None, 1, {}, llm_gateway, TEST_MODEL, EVALUATED_AT
    )

    assert result.score_total == 76.0
    assert result.score_breakdown == {
        "brand_reputation_prestige": 80.0,
        "company_scale": 70.0,
        "career_development_training_culture": 90.0,
        "sector_position": 60.0,
        "corporate_stability": 100.0,
        "external_signals": 50.0,
    }


def test_a_dimension_rated_exactly_zero_is_included_not_treated_as_insufficient():
    # Self-review kaygisi: `score=0.0` (gercek, cok dusuk ama GECERLI bir
    # puan) `None` (yetersiz bilgi) ile KARISTIRILMAMALIDIR. Uretim kodu
    # `if score is None: continue` kullanir (falsy kontrolu DEGIL) - bu
    # test, `if not score:` gibi alternatif (ve HATALI) bir uygulamanin
    # 0.0'i yanlislikla "yetersiz" sayip DISLAYACAGI senaryoyu acikca
    # kapsar. Yalnizca brand(.25, puan=0.0) ve scale(.20, puan=100.0)
    # derecelendirilmis; kalan agirlik toplami 0.45.
    # (0*.25 + 100*.20) / 0.45 = 20/0.45.
    inference = CompanyScoringInference(
        brand_reputation_prestige=_assessment(0.0),
        company_scale=_assessment(100.0),
        career_development_training_culture=_assessment(None, "Insufficient information."),
        sector_position=_assessment(None, "Insufficient information."),
        corporate_stability=_assessment(None, "Insufficient information."),
        external_signals=_assessment(None, "Insufficient information."),
    )
    llm_gateway = _FakeLLMGateway(result=inference)

    result = score_company(
        "Acme Corp", "Poorly regarded but scaled.", WEIGHTS, None, 1, {}, llm_gateway, TEST_MODEL,
        EVALUATED_AT,
    )

    assert result.score_total == 20 / 0.45
    assert result.score_breakdown["brand_reputation_prestige"] == 0.0


def test_weighted_score_renormalizes_over_remaining_weights_when_some_dimensions_are_unrated():
    # Yalnizca brand(.25)/scale(.20)/sector(.15) derecelendirilmis; kalan
    # agirlik toplami 0.60. (80*.25 + 70*.20 + 60*.15) / 0.60 = 43/0.60.
    inference = CompanyScoringInference(
        brand_reputation_prestige=_assessment(80.0),
        company_scale=_assessment(70.0),
        career_development_training_culture=_assessment(None, "Insufficient information."),
        sector_position=_assessment(60.0),
        corporate_stability=_assessment(None, "Insufficient information."),
        external_signals=_assessment(None, "Insufficient information."),
    )
    llm_gateway = _FakeLLMGateway(result=inference)

    result = score_company(
        "Acme Corp",
        "Very little is known.",
        WEIGHTS,
        None,
        1,
        {},
        llm_gateway,
        TEST_MODEL,
        EVALUATED_AT,
    )

    assert result.score_total == 43 / 0.60
    assert result.score_breakdown == {
        "brand_reputation_prestige": 80.0,
        "company_scale": 70.0,
        "career_development_training_culture": None,
        "sector_position": 60.0,
        "corporate_stability": None,
        "external_signals": None,
    }


def test_score_is_unrated_when_every_dimension_is_insufficient():
    inference = CompanyScoringInference(
        brand_reputation_prestige=_assessment(None, "Insufficient information."),
        company_scale=_assessment(None, "Insufficient information."),
        career_development_training_culture=_assessment(None, "Insufficient information."),
        sector_position=_assessment(None, "Insufficient information."),
        corporate_stability=_assessment(None, "Insufficient information."),
        external_signals=_assessment(None, "Insufficient information."),
    )
    llm_gateway = _FakeLLMGateway(result=inference)

    result = score_company(
        "Unknown Startup",
        "No information available.",
        WEIGHTS,
        None,
        1,
        {},
        llm_gateway,
        TEST_MODEL,
        EVALUATED_AT,
    )

    assert result.score_total is None


def test_score_is_unrated_when_llm_gateway_is_unavailable():
    # Gateway.generate() None doner (repair de basarisiz oldu) - M6.3/
    # M6.4'un "asla uydurma bir skor uretme" ilkesi burada da gecerlidir.
    llm_gateway = _FakeLLMGateway(result=None)

    result = score_company(
        "Acme Corp", "Founded 1998.", WEIGHTS, None, 1, {}, llm_gateway, TEST_MODEL, EVALUATED_AT
    )

    assert result.score_total is None
    assert result.score_breakdown == {}


def test_score_company_result_carries_the_given_cache_key_components():
    weight_profile_id = uuid4()
    llm_gateway = _FakeLLMGateway(result=_fully_rated_inference())

    result = score_company(
        "Acme Corp", "Founded 1998.", WEIGHTS, weight_profile_id, 3, {}, llm_gateway, TEST_MODEL,
        EVALUATED_AT,
    )

    assert result.company_id == "Acme Corp"
    assert result.weight_profile_id == weight_profile_id
    assert result.rubric_version == 3
    assert result.evaluated_at == EVALUATED_AT


def test_renders_the_company_scoring_template_with_the_given_company_details():
    llm_gateway = _FakeLLMGateway(result=_fully_rated_inference())

    score_company(
        "Acme Corp",
        "Founded 1998, ~2000 employees.",
        WEIGHTS,
        None,
        1,
        {},
        llm_gateway,
        TEST_MODEL,
        EVALUATED_AT,
    )

    assert len(llm_gateway.calls) == 1
    call = llm_gateway.calls[0]
    assert call["template_name"] == "company_scoring"
    assert call["response_model"] is CompanyScoringInference
    assert call["model"] == TEST_MODEL
    assert call["company_name"] == "Acme Corp"
    assert call["company_context"] == "Founded 1998, ~2000 employees."
