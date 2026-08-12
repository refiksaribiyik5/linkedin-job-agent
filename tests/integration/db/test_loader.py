"""config/loader.py icin entegrasyon testleri (Roadmap M2.2).

Roadmap M2.2 "Tamamlanma Dogrulamasi": "Bir config yuklenip context
olusturulduktan sonra DB'deki config degistirilir; ayni context'in hala
eski (donmus) degerleri tasidigi dogrulanir." Bu, asagidaki
`test_loaded_context_keeps_old_values_after_db_config_changes` testinin
tam olarak dogruladigi seydir.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from linkedinbot.config.loader import load_account_context
from linkedinbot.config.validator import ConfigValidationError
from linkedinbot.db.models import AccountConfigProfileOrm, AccountOrm, UserProfileOrm
from linkedinbot.domain.account_context import AccountContext

NOW = datetime(2026, 8, 8, tzinfo=UTC)


def _valid_config_profile_data() -> dict:
    """M1.4'un gercek seed edilmis account_config_profiles satiriyla
    ayni sekil (bkz. tests/unit/config/test_config_schema.py::_valid_data)."""
    return {
        "target_criteria": {
            "locations": ["Istanbul"],
            "departments": {"Sales & Business Development": ["Sales Executive"]},
            "experience_levels": ["Entry Level"],
            "workplace_types": ["On-site"],
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
            "linkedin_retry_attempts": 3,
            "llm_retry_attempts": 3,
            "retry_base_delay_ms": 500,
            "retry_max_delay_ms": 8000,
            "linkedin_consecutive_failure_threshold": 5,
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


def _make_active_config_profile(account_id, **field_overrides) -> AccountConfigProfileOrm:
    data = _valid_config_profile_data()
    data.update(field_overrides)
    return AccountConfigProfileOrm(
        account_id=account_id,
        config_version=1,
        is_active=True,
        validated_at=NOW,
        **data,
    )


def test_load_account_context_returns_fully_resolved_context(
    db_session: Session, account: AccountOrm
):

    db_session.add(
        UserProfileOrm(
            account_id=account.account_id,
            career_goals="Business Development",
            skills_summary="Satis",
            preferences_dealbreakers={"excluded_companies": [], "excluded_job_ids": []},
        )
    )
    db_session.add(_make_active_config_profile(account.account_id))
    db_session.flush()

    context = load_account_context(account.account_id, db_session)

    assert isinstance(context, AccountContext)
    assert context.account_id == account.account_id
    assert context.config_version == 1
    assert context.config_profile.thresholds.ai_match_score == 60
    assert context.user_profile.career_goals == "Business Development"


def test_load_account_context_raises_for_unknown_account(db_session: Session):
    with pytest.raises(ValueError, match="Hesap bulunamadi"):
        load_account_context(uuid4(), db_session)


def test_load_account_context_raises_when_no_user_profile(
    db_session: Session, account: AccountOrm
):
    db_session.add(_make_active_config_profile(account.account_id))
    db_session.flush()

    with pytest.raises(ValueError, match="kullanici profili bulunamadi"):
        load_account_context(account.account_id, db_session)


def test_load_account_context_raises_when_no_active_config_profile(
    db_session: Session, account: AccountOrm
):

    db_session.add(
        UserProfileOrm(
            account_id=account.account_id,
            career_goals="Business Development",
            skills_summary="Satis",
            preferences_dealbreakers={"excluded_companies": [], "excluded_job_ids": []},
        )
    )
    db_session.flush()

    with pytest.raises(ValueError, match="aktif bir config profili bulunamadi"):
        load_account_context(account.account_id, db_session)


def test_load_account_context_raises_when_only_an_inactive_config_profile_exists(
    db_session: Session, account: AccountOrm
):
    # Ic-denetimde bulunan eksik: onceki test yalnizca "hic satir yok"
    # senaryosunu kapsiyordu. Daha gerceci ve is_active=True FILTRESINI
    # asil sinayan durum, INAKTIF bir satirin var olup HICBIR aktif
    # satirin olmamasidir (orn. bir config versiyonu devre disi
    # birakilmis ama yenisi henuz aktiflestirilmemis).
    db_session.add(
        UserProfileOrm(
            account_id=account.account_id,
            career_goals="Business Development",
            skills_summary="Satis",
            preferences_dealbreakers={"excluded_companies": [], "excluded_job_ids": []},
        )
    )
    inactive_profile = _make_active_config_profile(account.account_id)
    inactive_profile.is_active = False
    db_session.add(inactive_profile)
    db_session.flush()

    with pytest.raises(ValueError, match="aktif bir config profili bulunamadi"):
        load_account_context(account.account_id, db_session)


def test_load_account_context_raises_config_validation_error_for_corrupted_db_row(
    db_session: Session, account: AccountOrm
):
    # TDD Section 23(b): "Calistirma baslangicinda - savunma amacli ikinci
    # bir dogrulama, DB'deki config'in yazma sonrasi bozulmamis oldugunu
    # garanti eder (fail-fast)." Bu satir dogrudan ORM ile (M2.1'in
    # validate_config()'unu ATLAYARAK) yazilir - orn. bir bug'in gecersiz
    # veri yazdigi senaryoyu simule eder.

    db_session.add(
        UserProfileOrm(
            account_id=account.account_id,
            career_goals="Business Development",
            skills_summary="Satis",
            preferences_dealbreakers={"excluded_companies": [], "excluded_job_ids": []},
        )
    )
    corrupted = _valid_config_profile_data()
    corrupted["thresholds"]["ai_match_score"] = 999  # gecersiz - 0-100 disi
    db_session.add(_make_active_config_profile(account.account_id, **corrupted))
    db_session.flush()

    with pytest.raises(ConfigValidationError):
        load_account_context(account.account_id, db_session)


def test_loaded_context_keeps_old_values_after_db_config_changes(
    db_session: Session, account: AccountOrm
):
    # Roadmap M2.2 "Tamamlanma Dogrulamasi" - birebir.

    db_session.add(
        UserProfileOrm(
            account_id=account.account_id,
            career_goals="Business Development",
            skills_summary="Satis",
            preferences_dealbreakers={"excluded_companies": [], "excluded_job_ids": []},
        )
    )
    orm_profile = _make_active_config_profile(account.account_id)
    db_session.add(orm_profile)
    db_session.flush()

    context = load_account_context(account.account_id, db_session)
    assert context.config_profile.thresholds.ai_match_score == 60

    # DB'deki config'i degistir (ayni satir,ayni oturum icinde).
    orm_profile.thresholds = {**orm_profile.thresholds, "ai_match_score": 70}
    db_session.flush()

    # Onceden yuklenen context, DEGISMEMIS eski degeri tasimaya devam eder.
    assert context.config_profile.thresholds.ai_match_score == 60

    # Ama YENI bir yukleme, guncel (degismis) degeri gorur - context'in
    # "donmus" olmasi, sistemin genel olarak degisikligi gormedigi
    # anlamina gelmez, yalnizca ONCEDEN olusturulmus context'in
    # etkilenmedigi anlamina gelir.
    fresh_context = load_account_context(account.account_id, db_session)
    assert fresh_context.config_profile.thresholds.ai_match_score == 70
