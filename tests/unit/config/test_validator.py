"""config/validator.py icin birim testleri (Roadmap M2.1).

Roadmap M2.1 "Tamamlanma Dogrulamasi": "Birim testleri en az bir gecerli
ve uc gecersiz (agirlik toplami hatali, esik araligi disi, tanimsiz
referans) config ile dogrulayiciyi calistirir." Asagidaki testler bu
dort durumu bire bir karsilar; ucuncusu (tanimsiz referans) kasitli
olarak uygulanmamis oldugu icin acikca `skip` edilir - bkz.
config/validator.py ve config/schema.py modul dokumanlari.
"""

from __future__ import annotations

import pytest

from linkedinbot.config.validator import ConfigValidationError, validate_config


def _valid_data() -> dict:
    """M1.4'un gercek seed edilmis account_config_profiles satirinin
    JSONB icerigiyle birebir ayni sekil (bkz. cli.py:seed(),
    config/system.defaults.yaml, config/accounts/default.account.yaml).
    """
    return {
        "target_criteria": {
            "locations": ["Istanbul"],
            "departments": {"Sales & Business Development": ["Sales Executive"]},
            "experience_levels": ["Entry Level", "Junior"],
            "workplace_types": ["On-site", "Hybrid"],
        },
        "weights_ai_match": {
            "department_role_relevance": 0.35,
            "experience_level_fit": 0.15,
            "location_fit": 0.10,
            "company_quality_contribution": 0.25,
            "career_goal_alignment": 0.15,
        },
        "weights_company_quality": {
            "brand_reputation_prestige": 0.25,
            "company_scale": 0.20,
            "career_development_training_culture": 0.20,
            "sector_position": 0.15,
            "corporate_stability": 0.10,
            "external_signals": 0.10,
        },
        "thresholds": {
            "company_quality_score": 50,
            "ai_match_score": 60,
            "department_confidence": 0.65,
            "borderline_band_width": 5,
            "company_score_reevaluation_window_days": 30,
        },
        "schedule": {"interval_days": 2, "jitter_minutes": 30},
        "collection_limits": {"max_jobs_per_run": 200},
        "notification_settings": {"enabled": False, "channels": []},
        "report_format_settings": {
            "format": "Markdown",
            "template": "default",
            "top_matches_count": 10,
            "language": "en",
        },
        "prompt_template_refs": {
            "department_matching": "department_matching.prompt.md",
            "experience_inference": "experience_inference.prompt.md",
            "company_scoring": "company_scoring.prompt.md",
            "ai_match_rationale": "ai_match_rationale.prompt.md",
        },
    }


def test_valid_config_is_accepted():
    # Roadmap M2.1: "en az bir gecerli ... config."
    profile = validate_config(_valid_data())
    assert profile.thresholds.ai_match_score == 60


def test_config_with_ai_match_weight_sum_not_100_percent_is_rejected():
    # Roadmap M2.1: "agirlik toplami hatali."
    data = _valid_data()
    data["weights_ai_match"]["location_fit"] = 0.50  # toplam artik 1.0 degil

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_config(data)

    assert any("AI Match Score" in error for error in exc_info.value.errors)


def test_config_with_company_quality_weight_sum_not_100_percent_is_rejected():
    data = _valid_data()
    data["weights_company_quality"]["external_signals"] = 0.50

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_config(data)

    assert any("Company Quality Score" in error for error in exc_info.value.errors)


def test_config_with_both_weight_categories_wrong_reports_both_not_just_one():
    # validator.py'nin KENDI toplama mantigi (schema.py'nin Pydantic-duzeyi
    # hata toplamasindan ayri bir kod yolu) - her iki agirlik kategorisi de
    # hatali oldugunda, yalnizca ilkini raporlayip digerini gizlememelidir.
    data = _valid_data()
    data["weights_ai_match"]["location_fit"] = 0.50
    data["weights_company_quality"]["external_signals"] = 0.50

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_config(data)

    assert any("AI Match Score" in error for error in exc_info.value.errors)
    assert any("Company Quality Score" in error for error in exc_info.value.errors)
    assert len(exc_info.value.errors) == 2


def test_config_with_threshold_out_of_range_is_rejected():
    # Roadmap M2.1: "esik araligi disi."
    data = _valid_data()
    data["thresholds"]["ai_match_score"] = 150

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_config(data)

    assert exc_info.value.errors  # en az bir hata mesaji var


def test_config_validation_error_aggregates_multiple_violations_not_just_the_first():
    # Roadmap M2.1 "Beklenen Sonuc": "...anlasilir bir hata mesaji uretir" -
    # yalnizca ilk ihlali gosterip gerisini gizlemek bu gereksinimi
    # karsilamaz; sekil-duzeyinde birden fazla ihlal AYNI ValidationError
    # icinde toplu olarak raporlanmalidir (Pydantic'in kendi davranisi).
    data = _valid_data()
    data["thresholds"]["ai_match_score"] = 150
    data["thresholds"]["department_confidence"] = 2.0

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_config(data)

    assert len(exc_info.value.errors) >= 2


def test_config_with_unrecognized_field_is_rejected_with_clear_message():
    # FR-13: "yanlis yazilmis bir alan adi" - config/schema.py'nin
    # extra="forbid" korumasi validate_config() araciligiyla da gecerlidir.
    data = _valid_data()
    data["thresholds"]["ai_match_scor"] = 60  # yazim hatasi

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_config(data)

    assert exc_info.value.errors


@pytest.mark.skip(
    reason=(
        "Roadmap M2.1'in 'tanimsiz bir departman referansi' maddesi kasitli "
        "olarak uygulanmamistir - M1.4'un target_criteria.departments alani "
        "bir referans degil dogrudan bir taksonomi tanimidir (PRD Section 17 "
        "acikca genisletilebilir/acik-uclu olarak tanimlar). Bu kontrolu "
        "eklemek M1.4'un onaylanmis veri modelini yeniden yapilandirmayi "
        "veya gereksinimi baska bir alana uygulanacak sekilde yeniden "
        "yorumlamayi gerektirirdi; proje talimati acikca ikisini de "
        "yasakladi. Bkz. config/schema.py ve config/validator.py modul "
        "dokumanlari."
    )
)
def test_config_with_undefined_department_reference_is_rejected():
    raise NotImplementedError
