from uuid import uuid4

import pytest
from pydantic import ValidationError

from linkedinbot.config.schema import (
    AccountConfigProfile,
    AIMatchWeights,
    CollectionLimits,
    CompanyQualityWeights,
    NotificationSettings,
    PromptTemplateRefs,
    ReportFormatSettings,
    Schedule,
    TargetCriteria,
    Thresholds,
)
from linkedinbot.domain.account_context import AccountContext
from linkedinbot.domain.job_posting import WorkplaceType
from linkedinbot.domain.user_profile import UserProfile


def _user_profile():
    return UserProfile(career_goals="Business Development", skills_summary="Satis")


def _config_profile():
    # M1.4'un gercek seed edilmis account_config_profiles satiriyla ayni
    # sekil (bkz. tests/unit/config/test_config_schema.py::_valid_data).
    return AccountConfigProfile(
        target_criteria=TargetCriteria(
            locations=["Istanbul"],
            departments={"Sales & Business Development": ["Sales Executive"]},
            experience_levels=["Entry Level"],
            workplace_types=[WorkplaceType.ON_SITE],
        ),
        weights_ai_match=AIMatchWeights(
            department_role_relevance=0.35,
            experience_level_fit=0.15,
            location_fit=0.10,
            company_quality_contribution=0.25,
            career_goal_alignment=0.15,
        ),
        weights_company_quality=CompanyQualityWeights(
            brand_reputation_prestige=0.25,
            company_scale=0.20,
            career_development_training_culture=0.20,
            sector_position=0.15,
            corporate_stability=0.10,
            external_signals=0.10,
        ),
        thresholds=Thresholds(
            company_quality_score=50,
            ai_match_score=60,
            department_confidence=0.65,
            department_confidence_tolerance=0.05,
            borderline_band_width=5,
            company_score_reevaluation_window_days=30,
        ),
        schedule=Schedule(interval_days=2, jitter_minutes=30),
        collection_limits=CollectionLimits(max_jobs_per_run=200),
        notification_settings=NotificationSettings(enabled=False, channels=[]),
        report_format_settings=ReportFormatSettings(
            format="Markdown", template="default", top_matches_count=10, language="en"
        ),
        prompt_template_refs=PromptTemplateRefs(
            department_matching="department_matching.prompt.md",
            experience_inference="experience_inference.prompt.md",
            company_scoring="company_scoring.prompt.md",
            ai_match_rationale="ai_match_rationale.prompt.md",
        ),
    )


def test_valid_account_context():
    context = AccountContext(
        account_id=uuid4(),
        user_profile=_user_profile(),
        config_version=1,
        config_profile=_config_profile(),
    )
    assert isinstance(context.user_profile, UserProfile)
    assert isinstance(context.config_profile, AccountConfigProfile)
    assert context.config_version == 1


def test_missing_user_profile_raises_validation_error():
    with pytest.raises(ValidationError):
        AccountContext(account_id=uuid4(), config_version=1, config_profile=_config_profile())


def test_missing_account_id_raises_validation_error():
    with pytest.raises(ValidationError):
        AccountContext(
            user_profile=_user_profile(), config_version=1, config_profile=_config_profile()
        )


def test_missing_config_profile_raises_validation_error():
    # M2.2: TDD Section 14'un AccountContext tanimi ("account_id +
    # cozumlenmis AccountConfigProfile + UserProfile") artik zorunlu
    # kilinir - config_profile'siz bir AccountContext gecersizdir.
    with pytest.raises(ValidationError):
        AccountContext(account_id=uuid4(), user_profile=_user_profile(), config_version=1)


def test_config_version_below_one_raises_validation_error():
    # account_config_profiles.config_version 1'den baslar.
    with pytest.raises(ValidationError):
        AccountContext(
            account_id=uuid4(),
            user_profile=_user_profile(),
            config_version=0,
            config_profile=_config_profile(),
        )


def test_account_context_has_exactly_the_m2_2_fields():
    # M2.2: config_profile (ve onun kimlik alani config_version) TDD
    # Section 14'un gerektirdigi sekilde eklendi; secrets_ref hala
    # eklenmedi (bkz. modul dokumani - altyapisal kavram, domain'e ait
    # degil, SecretsProvider port'u M2.3'te gelecek).
    field_names = set(AccountContext.model_fields)
    assert field_names == {"account_id", "user_profile", "config_version", "config_profile"}
