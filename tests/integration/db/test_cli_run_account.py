"""`cli.run_account()` icin entegrasyon testleri (Roadmap M9.7).

Bu dosya SADECE `run_account()`'in KENDI sorumlulugunu test eder:
`TriggerType.MANUAL` ile `orchestrator.run()`'u (M9.3, degistirilmemis)
cagirmak ve `is_bootstrap`'i FR-20/EDGE-13'un "Job History Store bu hesap
icin bos mu" tanimina gore hesaplamak. `orchestrator.run()`'un KENDI
pipeline/transaction/hata-siniflandirma davranisi ZATEN
`tests/integration/db/test_orchestrator.py`'de kapsamli sekilde test
edilmistir - burada TEKRAR EDILMEZ.

Bu projenin "her test dosyasi kendi sahtelerini tanimlar" konvansiyonuna
uygun olarak, `test_orchestrator.py`'nin fake'leri buraya import
EDILMEZ - AYNI desen (minimal, bu dosyanin KENDI ihtiyaci kadar) burada
yeniden tanimlanir.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from linkedinbot.adapters.reporting.filesystem_report_store import FilesystemReportStore
from linkedinbot.cli import run_account
from linkedinbot.db.models import AccountConfigProfileOrm, UserProfileOrm
from linkedinbot.db.repositories.company_repository import SqlAlchemyCompanyRepository
from linkedinbot.db.repositories.company_score_repository import SqlAlchemyCompanyScoreRepository
from linkedinbot.db.repositories.evaluated_job_repository import SqlAlchemyEvaluatedJobRepository
from linkedinbot.db.repositories.job_repository import SqlAlchemyJobRepository
from linkedinbot.db.repositories.report_repository import SqlAlchemyReportRepository
from linkedinbot.db.repositories.run_log_repository import SqlAlchemyRunLogRepository
from linkedinbot.domain.evaluated_job import MatchRationaleItem
from linkedinbot.domain.run_log import RunStatus, TriggerType
from linkedinbot.ports.linkedin_port import LinkedInPort
from linkedinbot.run.orchestrator import OrchestratorDependencies, RunAlreadyInProgressError
from linkedinbot.run.run_lock import RunLock
from linkedinbot.scoring.ai_matching import AIMatchRationaleInference, CareerGoalAlignmentInference
from linkedinbot.scoring.company_scoring import CompanyScoringInference, DimensionAssessment

NOW = datetime(2026, 8, 13, 9, 0, tzinfo=UTC)
LOCK_DURATION = timedelta(hours=1)


def _unique_job_and_card() -> tuple[str, str, str]:
    unique = uuid4().hex
    job_url = f"https://www.linkedin.com/jobs/view/{unique}"
    company = f"Acme Corp {unique}"
    card = f"""
<div>
  <div class="job-card-title">Sales Executive - Entry Level Program</div>
  <div class="job-card-company">{company}</div>
  <div class="job-card-location">Istanbul, Turkey</div>
  <div class="job-card-date">2 days ago</div>
  <div class="job-card-description">
    Entry Level opportunity to develop key accounts and drive business growth.
  </div>
  <a class="job-card-link" href="{job_url}">View</a>
</div>
"""
    return job_url, company, card


def _valid_config_profile_data() -> dict:
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


def _seed_account_context(db_session: Session, account_id: UUID) -> None:
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
            **_valid_config_profile_data(),
        )
    )
    db_session.flush()


class _FakeLinkedInPort(LinkedInPort):
    def __init__(self, cards_by_call: list[list[str]]) -> None:
        self._cards_by_call = list(cards_by_call)

    def ensure_session(self, account_id: UUID) -> None:
        raise NotImplementedError

    def validate(self, account_id: UUID) -> None:
        pass

    def search_jobs_page(
        self, account_id: UUID, location: str, keywords: str, page: int
    ) -> list[str]:
        if self._cards_by_call:
            return self._cards_by_call.pop(0)
        return []


class _ScriptedLLMGateway:
    def generate(self, template_name, response_model, model, **template_variables):
        if template_name == "department_matching":
            from linkedinbot.filtering.department_filter import DepartmentMatchInference

            return DepartmentMatchInference(
                matched_cluster="Sales & Business Development",
                confidence=0.9,
                reasoning="Directly matches the Sales & Business Development cluster.",
            )
        if template_name == "career_goal_alignment":
            return CareerGoalAlignmentInference(
                score=0.8, explanation="Strong alignment with stated career goals."
            )
        if template_name == "company_scoring":
            dimension = DimensionAssessment(score=80.0, justification="Well-regarded employer.")
            return CompanyScoringInference(
                brand_reputation_prestige=dimension,
                company_scale=dimension,
                career_development_training_culture=dimension,
                sector_position=dimension,
                corporate_stability=dimension,
                external_signals=dimension,
            )
        if template_name == "ai_match_rationale":
            return AIMatchRationaleInference(
                items=[
                    MatchRationaleItem(
                        component="Department/Role Relevance",
                        value="0.90",
                        explanation="Strong department match.",
                    ),
                    MatchRationaleItem(
                        component="Experience Level Fit",
                        value="Yes",
                        explanation="Matches an accepted entry-level posting.",
                    ),
                    MatchRationaleItem(
                        component="Location Fit", value="Yes", explanation="Located in Istanbul."
                    ),
                ]
            )
        raise AssertionError(f"Unexpected template_name in test: {template_name!r}")


class _CapturingStructuredLogger:
    def info(self, **kwargs):
        pass

    def warning(self, **kwargs):
        pass

    def error(self, **kwargs):
        pass


def _make_dependencies(db_session: Session, tmp_path, linkedin_port, llm_gateway):
    return OrchestratorDependencies(
        session=db_session,
        linkedin_port=linkedin_port,
        llm_gateway=llm_gateway,
        report_store=FilesystemReportStore(tmp_path),
        job_repository=SqlAlchemyJobRepository(db_session),
        company_repository=SqlAlchemyCompanyRepository(db_session),
        company_score_repository=SqlAlchemyCompanyScoreRepository(db_session),
        evaluated_job_repository=SqlAlchemyEvaluatedJobRepository(db_session),
        report_repository=SqlAlchemyReportRepository(db_session),
        run_log_repository=SqlAlchemyRunLogRepository(db_session),
        structured_logger=_CapturingStructuredLogger(),
    )


def test_run_account_uses_manual_trigger_type(db_session: Session, account, tmp_path):
    _, _company, card = _unique_job_and_card()
    _seed_account_context(db_session, account.account_id)
    dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[card]]), _ScriptedLLMGateway()
    )

    result = run_account(account.account_id, dependencies, NOW, LOCK_DURATION)

    assert result.trigger_type == TriggerType.MANUAL
    assert result.status == RunStatus.SUCCESS


def test_run_account_marks_a_first_run_as_bootstrap(db_session: Session, account, tmp_path):
    # FR-20/EDGE-13: "Job History Store" bu hesap icin bos - `run_account()`
    # bunu `is_bootstrap=True` olarak `orchestrator.run()`'a gecirmelidir.
    # Rapor icerigi (`compile_report()`, M8.2, degistirilmemis) "Bootstrap"
    # etiketiyle bunu GOZLEMLENEBILIR kilar (bkz. reporting/compiler.py
    # `_bracket_tag`).
    _, _company, card = _unique_job_and_card()
    _seed_account_context(db_session, account.account_id)
    dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[card]]), _ScriptedLLMGateway()
    )

    result = run_account(account.account_id, dependencies, NOW, LOCK_DURATION)

    report = dependencies.report_repository.get_by_run_id(account.account_id, result.run_id)
    assert report is not None
    content = report.storage_path.read_text(encoding="utf-8")
    assert "Bootstrap" in content


def test_run_account_does_not_mark_a_later_run_as_bootstrap(db_session: Session, account, tmp_path):
    _, _company_a, card_a = _unique_job_and_card()
    _seed_account_context(db_session, account.account_id)
    first_dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[card_a]]), _ScriptedLLMGateway()
    )
    run_account(account.account_id, first_dependencies, NOW, LOCK_DURATION)

    # Ikinci calistirma: hesabin ARTIK en az bir `evaluated_jobs` kaydi var -
    # Job History Store bu hesap icin ARTIK bos degil.
    _, _company_b, card_b = _unique_job_and_card()
    second_now = NOW + timedelta(days=2)
    second_dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[card_b]]), _ScriptedLLMGateway()
    )

    second_result = run_account(account.account_id, second_dependencies, second_now, LOCK_DURATION)

    report = second_dependencies.report_repository.get_by_run_id(
        account.account_id, second_result.run_id
    )
    assert report is not None
    content = report.storage_path.read_text(encoding="utf-8")
    assert "Bootstrap" not in content
    assert "[NEW]" in content


def test_run_account_propagates_run_already_in_progress_error(
    db_session: Session, account, tmp_path
):
    _seed_account_context(db_session, account.account_id)
    run_lock = RunLock(db_session)
    assert run_lock.acquire(account.account_id, "someone-else", NOW, LOCK_DURATION) is True
    db_session.flush()

    dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[]]), _ScriptedLLMGateway()
    )

    with pytest.raises(RunAlreadyInProgressError):
        run_account(account.account_id, dependencies, NOW, LOCK_DURATION)
