"""config/schema.py icin birim testleri (Roadmap M2.1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from linkedinbot.config.schema import (
    AccountConfigProfile,
    AIMatchWeights,
    CollectionLimits,
    NotificationSettings,
    PromptTemplateRefs,
    ReportFormatSettings,
    Schedule,
    TargetCriteria,
    Thresholds,
)


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
            "department_confidence_tolerance": 0.05,
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


def test_valid_profile_matching_m1_4_real_shape_is_accepted():
    profile = AccountConfigProfile(**_valid_data())
    assert profile.thresholds.ai_match_score == 60
    assert profile.target_criteria.locations == ["Istanbul"]


@pytest.mark.parametrize(
    "top_level_key",
    [
        "target_criteria",
        "weights_ai_match",
        "weights_company_quality",
        "thresholds",
        "schedule",
        "collection_limits",
        "notification_settings",
        "report_format_settings",
        "prompt_template_refs",
    ],
)
def test_missing_required_top_level_section_raises_validation_error(top_level_key):
    data = _valid_data()
    del data[top_level_key]
    with pytest.raises(ValidationError):
        AccountConfigProfile(**data)


def test_unrecognized_top_level_key_is_rejected():
    # FR-13: "yanlis yazilmis bir alan adi" - taninmayan bir anahtar
    # sessizce yutulmaz, acikca reddedilir.
    data = _valid_data()
    data["unexpected_typo_field"] = "should not be accepted"
    with pytest.raises(ValidationError):
        AccountConfigProfile(**data)


def test_unrecognized_nested_key_is_rejected():
    data = _valid_data()
    data["thresholds"]["typo_field"] = 123
    with pytest.raises(ValidationError):
        AccountConfigProfile(**data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("company_quality_score", -1),
        ("company_quality_score", 101),
        ("ai_match_score", -1),
        ("ai_match_score", 150),
        ("department_confidence", -0.01),
        ("department_confidence", 1.01),
        ("department_confidence_tolerance", -0.01),
        ("department_confidence_tolerance", 1.01),
        ("borderline_band_width", -1),
        ("company_score_reevaluation_window_days", 0),
    ],
)
def test_threshold_out_of_range_raises_validation_error(field, value):
    data = _valid_data()
    data["thresholds"][field] = value
    with pytest.raises(ValidationError):
        Thresholds(**data["thresholds"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("department_role_relevance", -0.1),
        ("department_role_relevance", 1.1),
    ],
)
def test_ai_match_weight_out_of_unit_range_raises_validation_error(field, value):
    data = _valid_data()
    data["weights_ai_match"][field] = value
    with pytest.raises(ValidationError):
        AIMatchWeights(**data["weights_ai_match"])


def test_experience_level_outside_prd_section_11_3_catalog_is_rejected():
    # Ic-denetimde bulunan eksik: Section 11.3, 17'nin tek degisiklik
    # ornegi bir CIKARMA'dir ("'Junior' cikarilmasi") - hicbir yerde
    # yeni bir deger EKLEME ornegi yoktur; bu, kumenin KAPALI oldugunu
    # gosterir. "Senior Manager" gibi tanimsiz bir deger acikca
    # reddedilmelidir (yazim hatasi/uydurma deger korumasi).
    data = _valid_data()
    data["target_criteria"]["experience_levels"] = ["Senior Manager"]
    with pytest.raises(ValidationError):
        TargetCriteria(**data["target_criteria"])


def test_workplace_type_outside_domain_enum_is_rejected():
    # PRD Section 15.2 zaten tam olarak {On-site, Hybrid, Remote} der;
    # bu M1.1'in WorkplaceType enum'unda somutlasmis. "Remotee" gibi bir
    # yazim hatasi acikca reddedilmelidir.
    data = _valid_data()
    data["target_criteria"]["workplace_types"] = ["Remotee"]
    with pytest.raises(ValidationError):
        TargetCriteria(**data["target_criteria"])


def test_empty_locations_list_raises_validation_error():
    data = _valid_data()
    data["target_criteria"]["locations"] = []
    with pytest.raises(ValidationError):
        TargetCriteria(**data["target_criteria"])


def test_empty_departments_dict_raises_validation_error():
    data = _valid_data()
    data["target_criteria"]["departments"] = {}
    with pytest.raises(ValidationError):
        TargetCriteria(**data["target_criteria"])


def test_department_with_empty_name_and_empty_title_list_raises_validation_error():
    # Field(min_length=1) uzerinde konteynerin DIS boyutunu kisitlar,
    # IC elemanlari degil - "" adinda, bos unvan listeli bir departman
    # (yapisal olarak "1 anahtar" sayilsa da anlamsiz/bozuk bir girdidir)
    # acikca reddedilmelidir.
    data = _valid_data()
    data["target_criteria"]["departments"] = {"": []}
    with pytest.raises(ValidationError):
        TargetCriteria(**data["target_criteria"])


def test_department_with_empty_title_string_raises_validation_error():
    data = _valid_data()
    data["target_criteria"]["departments"] = {"Sales": [""]}
    with pytest.raises(ValidationError):
        TargetCriteria(**data["target_criteria"])


def test_notification_channel_empty_string_raises_validation_error():
    data = _valid_data()
    data["notification_settings"] = {"enabled": True, "channels": [""]}
    with pytest.raises(ValidationError):
        NotificationSettings(**data["notification_settings"])


def test_schedule_non_positive_interval_days_raises_validation_error():
    with pytest.raises(ValidationError):
        Schedule(interval_days=0, jitter_minutes=30)


def test_collection_limits_non_positive_max_jobs_raises_validation_error():
    with pytest.raises(ValidationError):
        CollectionLimits(max_jobs_per_run=0)


def test_report_format_settings_non_positive_top_matches_count_raises_validation_error():
    with pytest.raises(ValidationError):
        ReportFormatSettings(
            format="Markdown", template="default", top_matches_count=0, language="en"
        )


def test_notification_settings_accepts_disabled_v1_default():
    settings = NotificationSettings(enabled=False, channels=[])
    assert settings.enabled is False
    assert settings.channels == []


def test_prompt_template_refs_requires_all_four_keys():
    with pytest.raises(ValidationError):
        PromptTemplateRefs(
            department_matching="department_matching.prompt.md",
            experience_inference="experience_inference.prompt.md",
            company_scoring="company_scoring.prompt.md",
            # ai_match_rationale eksik
        )
