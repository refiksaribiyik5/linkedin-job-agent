"""M1.2 semasi icin entegrasyon testleri.

TDD Section 2 SQLite'i bilincli olarak eledigi icin (Section 12.4/15.0'in
JSONB + kismi unique index gereksinimleri Postgre'ye ozgudur), bu testler
gercek M0.2 Postgres konteynerine karsi calisir, sahte/hafif bir DB'ye
karsi degil.

Roadmap M1.2 "Tamamlanma Dogrulamasi": "Sema, TDD Section 15 tablolariyla
satir satir karsilastirilir; her tabloya bir ornek satir eklenip okunarak
temel butunluk dogrulanir." Asagidaki testler bunu, ayrica iki mimari
bosluk cozumunun (company_scores kismi unique index'leri, composite FK'ler)
fiilen calistigini kanitlayarak yapar.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from linkedinbot.db.engine import create_db_engine, create_session_factory
from linkedinbot.db.models import (
    AccountConfigProfileOrm,
    AccountOrm,
    CompanyOrm,
    CompanyScoreOrm,
    EvaluatedJobOrm,
    JobPostingOrm,
    LinkedInSessionOrm,
    ReportOrm,
    RunLockOrm,
    RunLogOrm,
    SessionStatus,
    UserProfileOrm,
)
from linkedinbot.domain.evaluated_job import JobStatus
from linkedinbot.domain.run_log import RunStatus, TriggerType

NOW = datetime.now(UTC)


@pytest.fixture
def db_session():
    """Gercek M0.2 Postgres konteynerine karsi, her test sonunda geri
    alinan (rollback) bir transaction icinde calisan oturum.
    """
    engine = create_db_engine()
    factory = create_session_factory(engine)
    session: Session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


@pytest.fixture
def account(db_session: Session) -> AccountOrm:
    acc = AccountOrm(display_name="Test Hesabi", created_at=NOW, status="active")
    db_session.add(acc)
    db_session.flush()
    return acc


def test_all_eleven_tables_exist(db_session: Session):
    # Roadmap M1.2: "Sema, TDD Section 15 tablolariyla satir satir karsilastirilir."
    rows = db_session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    ).fetchall()
    table_names = {r[0] for r in rows}
    expected = {
        "accounts",
        "user_profiles",
        "account_config_profiles",
        "linkedin_sessions",
        "evaluated_jobs",
        "reports",
        "run_logs",
        "run_locks",
        "companies",
        "company_scores",
        "job_postings",
    }
    assert expected <= table_names


def test_insert_and_read_back_one_row_per_table(db_session: Session, account: AccountOrm):
    # Roadmap M1.2: "her tabloya bir ornek satir eklenip okunarak temel
    # butunluk dogrulanir."
    user_profile = UserProfileOrm(
        account_id=account.account_id,
        career_goals="Business Development",
        skills_summary="Satis",
        preferences_dealbreakers={"excluded_companies": [], "excluded_job_ids": []},
    )
    config_profile = AccountConfigProfileOrm(
        account_id=account.account_id,
        config_version=1,
        target_criteria={"departments": [], "locations": ["Istanbul"], "experience_levels": []},
        weights_ai_match={},
        weights_company_quality={},
        thresholds={},
        schedule={},
        collection_limits={},
        notification_settings={},
        report_format_settings={},
        prompt_template_refs={},
        is_active=True,
        validated_at=NOW,
    )
    session_row = LinkedInSessionOrm(
        account_id=account.account_id, session_status=SessionStatus.UNKNOWN
    )
    run_lock = RunLockOrm(account_id=account.account_id)
    company = CompanyOrm(
        company_id="company-1", name="Ornek A.S.", first_seen_at=NOW, last_updated_at=NOW
    )
    company_score = CompanyScoreOrm(
        company_id=company.company_id,
        weight_profile_id=None,
        rubric_version=1,
        score_total=85,
        score_breakdown={"brand": 90},
        evaluated_at=NOW,
    )
    job = JobPostingOrm(
        job_id="linkedin-1",
        title="Business Development Executive",
        company_id=company.company_id,
        location_text="Istanbul",
        posted_date=NOW,
        description="Aciklama",
        application_url="https://www.linkedin.com/jobs/view/1",
        collected_at=NOW,
        content_hash="hash-1",
    )
    db_session.add_all(
        [user_profile, config_profile, session_row, run_lock, company, company_score, job]
    )
    db_session.flush()

    run_log = RunLogOrm(
        account_id=account.account_id,
        trigger_type=TriggerType.MANUAL,
        started_at=NOW,
        ended_at=NOW,
        status=RunStatus.SUCCESS,
    )
    db_session.add(run_log)
    db_session.flush()

    evaluated_job = EvaluatedJobOrm(
        account_id=account.account_id,
        job_id=job.job_id,
        company_id=company.company_id,
        status=JobStatus.NEW,
        first_seen_at=NOW,
        last_seen_at=NOW,
        content_hash_at_evaluation=job.content_hash,
        config_version_used=config_profile.config_version,
    )
    report = ReportOrm(
        account_id=account.account_id,
        run_id=run_log.run_id,
        generated_at=NOW,
        config_snapshot_ref=config_profile.config_version,
        storage_path=f"reports/{account.account_id}/report.md",
    )
    db_session.add_all([evaluated_job, report])
    db_session.flush()

    # Okuma dogrulamasi: her satir geri okunabiliyor mu?
    assert db_session.get(AccountOrm, account.account_id) is not None
    assert db_session.get(UserProfileOrm, account.account_id) is not None
    assert db_session.get(AccountConfigProfileOrm, (account.account_id, 1)) is not None
    assert db_session.get(LinkedInSessionOrm, account.account_id) is not None
    assert db_session.get(RunLockOrm, account.account_id) is not None
    assert db_session.get(CompanyOrm, "company-1") is not None
    assert db_session.get(CompanyScoreOrm, company_score.id) is not None
    assert db_session.get(JobPostingOrm, "linkedin-1") is not None
    assert db_session.get(RunLogOrm, run_log.run_id) is not None
    assert db_session.get(EvaluatedJobOrm, evaluated_job.id) is not None
    read_back_report = db_session.get(ReportOrm, report.report_id)
    assert read_back_report is not None
    assert read_back_report.run_id == run_log.run_id


def test_company_scores_default_uniqueness_is_enforced(db_session: Session):
    # Section 12.4: sistem varsayilani icin sirket+rubric basina en fazla
    # bir paylasilan skor (weight_profile_id IS NULL).
    company = CompanyOrm(
        company_id="company-dup", name="Ornek A.S.", first_seen_at=NOW, last_updated_at=NOW
    )
    db_session.add(company)
    db_session.flush()

    db_session.add(
        CompanyScoreOrm(
            company_id=company.company_id,
            weight_profile_id=None,
            rubric_version=1,
            evaluated_at=NOW,
        )
    )
    db_session.flush()

    db_session.add(
        CompanyScoreOrm(
            company_id=company.company_id,
            weight_profile_id=None,
            rubric_version=1,
            evaluated_at=NOW,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_company_scores_allows_multiple_custom_weight_profiles(db_session: Session):
    # Farkli weight_profile_id degerleri (hesaba ozel agirliklar) ayni
    # sirket+rubric icin coexist edebilmelidir.
    company = CompanyOrm(
        company_id="company-multi", name="Ornek A.S.", first_seen_at=NOW, last_updated_at=NOW
    )
    db_session.add(company)
    db_session.flush()

    db_session.add(
        CompanyScoreOrm(
            company_id=company.company_id,
            weight_profile_id=uuid.uuid4(),
            rubric_version=1,
            evaluated_at=NOW,
        )
    )
    db_session.add(
        CompanyScoreOrm(
            company_id=company.company_id,
            weight_profile_id=uuid.uuid4(),
            rubric_version=1,
            evaluated_at=NOW,
        )
    )
    db_session.flush()  # hata firlatmamali


def test_evaluated_jobs_config_version_composite_fk_is_enforced(
    db_session: Session, account: AccountOrm
):
    company = CompanyOrm(
        company_id="company-fk", name="Ornek A.S.", first_seen_at=NOW, last_updated_at=NOW
    )
    job = JobPostingOrm(
        job_id="linkedin-fk",
        title="t",
        company_id=company.company_id,
        location_text="Istanbul",
        posted_date=NOW,
        description="d",
        application_url="https://example.com",
        collected_at=NOW,
        content_hash="h",
    )
    db_session.add_all([company, job])
    db_session.flush()

    # account_config_profiles'ta hic (account_id, config_version=99) yok -
    # bilesik FK bunu reddetmelidir.
    db_session.add(
        EvaluatedJobOrm(
            account_id=account.account_id,
            job_id=job.job_id,
            company_id=company.company_id,
            status=JobStatus.NEW,
            first_seen_at=NOW,
            last_seen_at=NOW,
            content_hash_at_evaluation="h",
            config_version_used=99,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_evaluated_jobs_unique_account_job_constraint(db_session: Session, account: AccountOrm):
    company = CompanyOrm(
        company_id="company-uniq", name="Ornek A.S.", first_seen_at=NOW, last_updated_at=NOW
    )
    job = JobPostingOrm(
        job_id="linkedin-uniq",
        title="t",
        company_id=company.company_id,
        location_text="Istanbul",
        posted_date=NOW,
        description="d",
        application_url="https://example.com",
        collected_at=NOW,
        content_hash="h",
    )
    config_profile = AccountConfigProfileOrm(
        account_id=account.account_id,
        config_version=1,
        target_criteria={},
        weights_ai_match={},
        weights_company_quality={},
        thresholds={},
        schedule={},
        collection_limits={},
        notification_settings={},
        report_format_settings={},
        prompt_template_refs={},
        is_active=True,
        validated_at=NOW,
    )
    db_session.add_all([company, job, config_profile])
    db_session.flush()

    kwargs = dict(
        account_id=account.account_id,
        job_id=job.job_id,
        company_id=company.company_id,
        status=JobStatus.NEW,
        first_seen_at=NOW,
        last_seen_at=NOW,
        content_hash_at_evaluation="h",
        config_version_used=1,
    )
    db_session.add(EvaluatedJobOrm(**kwargs))
    db_session.flush()

    db_session.add(EvaluatedJobOrm(**kwargs))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_reports_run_id_uniqueness_enforces_one_to_one_with_run_logs(
    db_session: Session, account: AccountOrm
):
    # TDD Section 16 (v1.1): run_logs (1) -> (1) reports.
    config_profile = AccountConfigProfileOrm(
        account_id=account.account_id,
        config_version=1,
        target_criteria={},
        weights_ai_match={},
        weights_company_quality={},
        thresholds={},
        schedule={},
        collection_limits={},
        notification_settings={},
        report_format_settings={},
        prompt_template_refs={},
        is_active=True,
        validated_at=NOW,
    )
    run_log = RunLogOrm(
        account_id=account.account_id,
        trigger_type=TriggerType.SCHEDULED,
        started_at=NOW,
        ended_at=NOW,
        status=RunStatus.SUCCESS,
    )
    db_session.add_all([config_profile, run_log])
    db_session.flush()

    report_kwargs = dict(
        account_id=account.account_id,
        run_id=run_log.run_id,
        generated_at=NOW,
        config_snapshot_ref=1,
        storage_path="reports/x.md",
    )
    db_session.add(ReportOrm(**report_kwargs))
    db_session.flush()

    db_session.add(ReportOrm(**{**report_kwargs, "storage_path": "reports/y.md"}))
    with pytest.raises(IntegrityError):
        db_session.flush()
