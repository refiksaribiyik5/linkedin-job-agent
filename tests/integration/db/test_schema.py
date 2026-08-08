"""M1.2 semasi icin entegrasyon testleri.

TDD Section 2 SQLite'i bilincli olarak eledigi icin (Section 12.4/15.0'in
JSONB + kismi unique index gereksinimleri Postgre'ye ozgudur), bu testler
gercek M0.2 Postgres konteynerine karsi calisir, sahte/hafif bir DB'ye
karsi degil.

Roadmap M1.2 "Tamamlanma Dogrulamasi": "Sema, TDD Section 15 tablolariyla
satir satir karsilastirilir; her tabloya bir ornek satir eklenip okunarak
temel butunluk dogrulanir." Asagidaki testler bunu, ayrica su noktalarin
fiilen calistigini kanitlayarak yapar:

- iki mimari bosluk cozumu (company_scores kismi unique index'leri,
  composite FK'ler);
- uretim-oncesi incelemede bulunan BLOCKER duzeltmesi: ENUM sutunlari
  artik Python enum uyesinin `.name`'i degil `.value`'su ile saklanir
  (bkz. test_enum_columns_store_prd_specified_values_not_python_names);
- ayni incelemede bulunan iki MAJOR duzeltmesi: account_config_profiles
  icin "tam olarak bir aktif profil" kisiti ve skor/sayac alanlari icin
  CHECK kisitlari;
- semanin nullable-alan tasarim niyetinin (erken elenen/henuz
  puanlanmamis ilanlar) fiilen calistigi.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
from linkedinbot.domain.job_posting import WorkplaceType
from linkedinbot.domain.run_log import RunStatus, TriggerType

# engine/db_session/account/make_config_profile fixture'lari artik
# conftest.py'de (M1.3'te birden fazla test dosyasi tarafindan paylasilmak
# icin tasindi).
NOW = datetime.now(UTC)


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


def test_insert_and_read_back_one_row_per_table(
    db_session: Session, account: AccountOrm, make_config_profile
):
    # Roadmap M1.2: "her tabloya bir ornek satir eklenip okunarak temel
    # butunluk dogrulanir."
    user_profile = UserProfileOrm(
        account_id=account.account_id,
        career_goals="Business Development",
        skills_summary="Satis",
        preferences_dealbreakers={"excluded_companies": [], "excluded_job_ids": []},
    )
    config_profile = make_config_profile(account.account_id)
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


# ---------------------------------------------------------------------------
# BLOCKER duzeltmesi: ENUM sutunlari .value ile saklanir, .name ile degil.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("table", "column", "python_value", "expected_raw_value"),
    [
        ("job_status_probe", "status", JobStatus.NEW, "New"),
        ("run_status_probe", "status", RunStatus.SUCCESS, "Success"),
        ("trigger_type_probe", "trigger_type", TriggerType.SCHEDULED, "Scheduled"),
        ("session_status_probe", "session_status", SessionStatus.VALID, "valid"),
        ("workplace_type_probe", "workplace_type", WorkplaceType.HYBRID, "Hybrid"),
    ],
)
def test_enum_columns_store_prd_specified_values_not_python_member_names(
    db_session: Session,
    account: AccountOrm,
    make_config_profile,
    table: str,
    column: str,
    python_value,
    expected_raw_value: str,
):
    """Regresyon testi: SQLAlchemy'nin `sa.Enum(...)` varsayilani, enum
    uyesinin `.name`'ini (orn. "HYBRID") native Postgres ENUM etiketi
    olarak saklar -- `.value`'yu (orn. "Hybrid", PRD'nin belirttigi
    deger) DEGIL. Bu, gercek bir M1.2 incelemesinde veritabanina
    yazilip raw SQL ile okunarak dogrulanmis bir hataydi. Duzeltme
    (`values_callable`, bkz. db/models.py) burada her 5 enum turu icin
    ayri ayri, ORM'i atlayip DOGRUDAN ham SQL ile okuyarak dogrulanir --
    yalnizca ORM uzerinden okumak bu hatayi YAKALAMAZDI (SQLAlchemy
    kendi secimiyle kendi icinde tutarlidir).
    """
    company = CompanyOrm(
        company_id=f"company-{table}", name="x", first_seen_at=NOW, last_updated_at=NOW
    )
    job = JobPostingOrm(
        job_id=f"job-{table}",
        title="t",
        company_id=company.company_id,
        location_text="Istanbul",
        workplace_type=WorkplaceType.HYBRID,
        posted_date=NOW,
        description="d",
        application_url="https://example.com",
        collected_at=NOW,
        content_hash="h",
    )
    config_profile = make_config_profile(account.account_id)
    db_session.add_all([company, job, config_profile])
    db_session.flush()

    run_log = RunLogOrm(
        account_id=account.account_id,
        trigger_type=TriggerType.SCHEDULED,
        started_at=NOW,
        ended_at=NOW,
        status=RunStatus.SUCCESS,
    )
    evaluated_job = EvaluatedJobOrm(
        account_id=account.account_id,
        job_id=job.job_id,
        company_id=company.company_id,
        status=JobStatus.NEW,
        first_seen_at=NOW,
        last_seen_at=NOW,
        content_hash_at_evaluation="h",
        config_version_used=config_profile.config_version,
    )
    session_row = LinkedInSessionOrm(
        account_id=account.account_id, session_status=SessionStatus.VALID
    )
    db_session.add_all([run_log, evaluated_job, session_row])
    db_session.flush()

    raw_value_by_table = {
        "job_status_probe": db_session.execute(
            text("SELECT status::text FROM evaluated_jobs WHERE id = :id"),
            {"id": evaluated_job.id},
        ).scalar(),
        "run_status_probe": db_session.execute(
            text("SELECT status::text FROM run_logs WHERE run_id = :id"), {"id": run_log.run_id}
        ).scalar(),
        "trigger_type_probe": db_session.execute(
            text("SELECT trigger_type::text FROM run_logs WHERE run_id = :id"),
            {"id": run_log.run_id},
        ).scalar(),
        "session_status_probe": db_session.execute(
            text("SELECT session_status::text FROM linkedin_sessions WHERE account_id = :id"),
            {"id": account.account_id},
        ).scalar(),
        "workplace_type_probe": db_session.execute(
            text("SELECT workplace_type::text FROM job_postings WHERE job_id = :id"),
            {"id": job.job_id},
        ).scalar(),
    }
    assert raw_value_by_table[table] == expected_raw_value


# ---------------------------------------------------------------------------
# MAJOR duzeltmesi: account_config_profiles "tam olarak bir aktif profil".
# ---------------------------------------------------------------------------


def test_only_one_active_config_profile_per_account_is_enforced(
    db_session: Session, account: AccountOrm, make_config_profile
):
    # TDD Section 16: "tam olarak bir tanesi is_active=true".
    db_session.add(make_config_profile(account.account_id, config_version=1, is_active=True))
    db_session.flush()

    db_session.add(make_config_profile(account.account_id, config_version=2, is_active=True))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_multiple_inactive_config_profiles_are_allowed(
    db_session: Session, account: AccountOrm, make_config_profile
):
    # Gecmis (artik aktif olmayan) config versiyonlari NFR-11 geregi
    # silinmez; kismi index yalnizca is_active=true satirlari sinirlar.
    db_session.add(make_config_profile(account.account_id, config_version=1, is_active=False))
    db_session.add(make_config_profile(account.account_id, config_version=2, is_active=False))
    db_session.add(make_config_profile(account.account_id, config_version=3, is_active=True))
    db_session.flush()  # hata firlatmamali


def test_two_different_accounts_can_each_have_their_own_active_profile(db_session: Session):
    # Kismi index account_id'ye gore kapsamlanir (global degil).
    acc1 = AccountOrm(display_name="A", created_at=NOW, status="active")
    acc2 = AccountOrm(display_name="B", created_at=NOW, status="active")
    db_session.add_all([acc1, acc2])
    db_session.flush()

    db_session.add(
        AccountConfigProfileOrm(
            account_id=acc1.account_id,
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
    )
    db_session.add(
        AccountConfigProfileOrm(
            account_id=acc2.account_id,
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
    )
    db_session.flush()  # hata firlatmamali


# ---------------------------------------------------------------------------
# MAJOR duzeltmesi: sayisal alanlar icin CHECK kisitlari (savunma derinligi).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("out_of_range_score", [-1, 100.01, 500])
def test_ai_match_score_out_of_range_is_rejected_at_db_level(
    db_session: Session, account: AccountOrm, out_of_range_score
):
    # M1.1'in Pydantic dogrulamasi (ge=0, le=100) yalnizca uygulama
    # katmaninda calisir; bu test DB'nin de ayni kurali savundugunu
    # dogrudan (Pydantic'i atlayarak) kanitlar.
    company = CompanyOrm(company_id="c-range", name="x", first_seen_at=NOW, last_updated_at=NOW)
    job = JobPostingOrm(
        job_id="j-range",
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

    db_session.add(
        EvaluatedJobOrm(
            account_id=account.account_id,
            job_id=job.job_id,
            company_id=company.company_id,
            ai_match_score=out_of_range_score,
            status=JobStatus.NEW,
            first_seen_at=NOW,
            last_seen_at=NOW,
            content_hash_at_evaluation="h",
            config_version_used=1,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_company_score_total_out_of_range_is_rejected_at_db_level(db_session: Session):
    company = CompanyOrm(
        company_id="c-score-range", name="x", first_seen_at=NOW, last_updated_at=NOW
    )
    db_session.add(company)
    db_session.flush()

    db_session.add(
        CompanyScoreOrm(
            company_id=company.company_id,
            weight_profile_id=None,
            rubric_version=1,
            score_total=150,
            evaluated_at=NOW,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize(
    "field", ["jobs_collected", "jobs_filtered", "jobs_new", "jobs_closed"]
)
def test_run_log_negative_job_counts_are_rejected_at_db_level(
    db_session: Session, account: AccountOrm, field: str
):
    kwargs = {
        "account_id": account.account_id,
        "trigger_type": TriggerType.MANUAL,
        "started_at": NOW,
        "ended_at": NOW,
        "status": RunStatus.SUCCESS,
        field: -1,
    }
    db_session.add(RunLogOrm(**kwargs))
    with pytest.raises(IntegrityError):
        db_session.flush()


# ---------------------------------------------------------------------------
# MAJOR duzeltmesi: semanin nullable-alan tasarim niyeti fiilen test edilir.
# ---------------------------------------------------------------------------


def test_evaluated_job_with_all_optional_fields_null_persists_correctly(
    db_session: Session, account: AccountOrm, make_config_profile
):
    # Section 11.4: Location/Experience filtresinde elenen bir ilan hicbir
    # zaman ai_match_score, match_rationale, department_cluster veya
    # filter_result_detail almaz. Bu, semanin nullable tasarimininin
    # var olma nedenidir; simdiye kadar hicbir test bunu dogrudan
    # sinamamisti.
    company = CompanyOrm(company_id="c-null", name="x", first_seen_at=NOW, last_updated_at=NOW)
    job = JobPostingOrm(
        job_id="j-null",
        title="t",
        company_id=company.company_id,
        location_text="Ankara",
        posted_date=NOW,
        description="d",
        application_url="https://example.com",
        collected_at=NOW,
        content_hash="h",
    )
    config_profile = make_config_profile(account.account_id)
    db_session.add_all([company, job, config_profile])
    db_session.flush()

    rejected_job = EvaluatedJobOrm(
        account_id=account.account_id,
        job_id=job.job_id,
        company_id=company.company_id,
        ai_match_score=None,
        match_rationale=None,
        department_cluster=None,
        filter_result_detail=None,
        status=JobStatus.CLOSED,
        is_borderline=False,
        first_seen_at=NOW,
        last_seen_at=NOW,
        content_hash_at_evaluation="h",
        config_version_used=1,
    )
    db_session.add(rejected_job)
    db_session.flush()
    db_session.expire_all()

    read_back = db_session.get(EvaluatedJobOrm, rejected_job.id)
    assert read_back.ai_match_score is None
    assert read_back.match_rationale is None
    assert read_back.department_cluster is None
    assert read_back.filter_result_detail is None


def test_job_posting_with_all_optional_fields_null_persists_correctly(db_session: Session):
    # FR-2: yalnizca baslik/sirket/lokasyon/tarih/aciklama/link zorunludur;
    # workplace_type/employment_type/easy_apply LinkedIn'de her zaman
    # mevcut olmayabilir.
    company = CompanyOrm(
        company_id="c-null-job", name="x", first_seen_at=NOW, last_updated_at=NOW
    )
    job = JobPostingOrm(
        job_id="j-null-optional",
        title="t",
        company_id=company.company_id,
        location_text="Istanbul",
        workplace_type=None,
        employment_type=None,
        easy_apply=None,
        posted_date=NOW,
        description="d",
        application_url="https://example.com",
        collected_at=NOW,
        content_hash="h",
    )
    db_session.add_all([company, job])
    db_session.flush()
    db_session.expire_all()

    read_back = db_session.get(JobPostingOrm, "j-null-optional")
    assert read_back.workplace_type is None
    assert read_back.employment_type is None
    assert read_back.easy_apply is None


# ---------------------------------------------------------------------------
# MINOR iyilestirmesi: surrogate PK'ler icin server-side varsayilan.
# ---------------------------------------------------------------------------


def test_uuid_primary_key_has_server_side_default_for_non_orm_inserts(db_session: Session):
    # ORM disi bir ekleme yolu (raw SQL, gelecekte baska bir servis)
    # account_id sutununu hic belirtmezse, Postgres'in kendisi
    # gen_random_uuid() ile bir deger uretmelidir (yalnizca Python-tarafi
    # default=uuid.uuid4'e guvenmek yerine).
    result = db_session.execute(
        text(
            "INSERT INTO accounts (display_name, created_at, status) "
            "VALUES (:name, :created_at, :status) RETURNING account_id"
        ),
        {"name": "raw-insert-test", "created_at": NOW, "status": "active"},
    )
    generated_id = result.scalar()
    assert generated_id is not None
    assert isinstance(generated_id, uuid.UUID)


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

    profile_a, profile_b = uuid.uuid4(), uuid.uuid4()
    db_session.add(
        CompanyScoreOrm(
            company_id=company.company_id,
            weight_profile_id=profile_a,
            rubric_version=1,
            evaluated_at=NOW,
        )
    )
    db_session.add(
        CompanyScoreOrm(
            company_id=company.company_id,
            weight_profile_id=profile_b,
            rubric_version=1,
            evaluated_at=NOW,
        )
    )
    db_session.flush()

    # Zayif dogrulama riski: yalnizca "hata firlatilmadi" degil, iki
    # AYRI satirin gercekten var oldugunu da dogrudan sayarak kanitla.
    stored_profile_ids = set(
        db_session.execute(
            text("SELECT weight_profile_id FROM company_scores WHERE company_id = :cid"),
            {"cid": company.company_id},
        ).scalars()
    )
    assert stored_profile_ids == {profile_a, profile_b}


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


def test_evaluated_jobs_unique_account_job_constraint(
    db_session: Session, account: AccountOrm, make_config_profile
):
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
    config_profile = make_config_profile(account.account_id)
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
    db_session: Session, account: AccountOrm, make_config_profile
):
    # TDD Section 16 (v1.1): run_logs (1) -> (1) reports.
    config_profile = make_config_profile(account.account_id)
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
