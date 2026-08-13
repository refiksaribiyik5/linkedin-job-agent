"""`main._load_schedule_settings()` icin entegrasyon testi (Roadmap M10.1).

`_load_schedule_settings()`'in TEK sorumlulugu, `load_account_context()`'in
(M2.2, degistirilmemis) dondurdugu `config_profile.schedule`'i (interval_days,
jitter_minutes) `run_forever()`'in ihtiyac duydugu iki `timedelta`'ya
cevirmektir - `load_account_context()`'in KENDI dogrulama/oncelik davranisi
zaten M2.2'nin kendi testlerinde kapsanmistir, burada TEKRAR EDILMEZ.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from linkedinbot.db.models import AccountConfigProfileOrm, UserProfileOrm
from linkedinbot.main import _load_schedule_settings

NOW = datetime(2026, 8, 13, 9, 0, tzinfo=UTC)


def _valid_config_profile_data(interval_days: int, jitter_minutes: int) -> dict:
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
        "schedule": {"interval_days": interval_days, "jitter_minutes": jitter_minutes},
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


def _seed_account_context(
    db_session: Session, account_id: UUID, interval_days: int, jitter_minutes: int
) -> None:
    db_session.add(
        UserProfileOrm(
            account_id=account_id,
            career_goals="Grow into a business development leadership role.",
            skills_summary="Sales, account management, negotiation.",
            preferences_dealbreakers={"excluded_companies": [], "excluded_job_ids": []},
        )
    )
    db_session.add(
        AccountConfigProfileOrm(
            account_id=account_id,
            config_version=1,
            is_active=True,
            validated_at=NOW,
            **_valid_config_profile_data(interval_days, jitter_minutes),
        )
    )
    db_session.flush()


def test_load_schedule_settings_maps_interval_days_and_jitter_minutes_to_timedeltas(
    db_session: Session, account
):
    _seed_account_context(db_session, account.account_id, interval_days=2, jitter_minutes=30)

    interval, jitter_window = _load_schedule_settings(account.account_id, db_session)

    assert interval == timedelta(days=2)
    assert jitter_window == timedelta(minutes=30)


def test_load_schedule_settings_reflects_a_different_configured_schedule(
    db_session: Session, account
):
    _seed_account_context(db_session, account.account_id, interval_days=5, jitter_minutes=15)

    interval, jitter_window = _load_schedule_settings(account.account_id, db_session)

    assert interval == timedelta(days=5)
    assert jitter_window == timedelta(minutes=15)
