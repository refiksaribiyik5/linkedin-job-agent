"""Rapor kalicilik entegrasyon testi (Roadmap M8.3, FR-17, TDD Section 18).

Roadmap M8.3 "Beklenen Sonuc": "Iki ardisik derleme, iki ayri dosya ve iki
ayri `reports` satiri (dogru `config_snapshot_ref` ile) uretir."
"Tamamlanma Dogrulamasi": "Derleyici arka arkaya iki kez calistirilir;
iki farkli dosya ve iki farkli DB satiri dogrulanir."

Bu test, M8.2'nin `compile_report()`'unu (degistirilmemis), M8.3'un YENI
`FilesystemReportStore`'unu (gercek `tmp_path` ile, DB'ye dokunmadan) ve
M1.3'un ZATEN VAR OLAN `SqlAlchemyReportRepository`'sini (degistirilmemis,
gercek bir DB oturumuyla) BIRLIKTE, art arda IKI KEZ calistirarak Roadmap'in
tam olarak istedigi senaryoyu dogrular.

Kasitli olarak yapilmayan sey: M8.2 (compile_report) + M8.3 (ReportStore +
ReportRepositoryPort) + idempotency kontrolunu (TDD Section 18 adim 5) TEK
bir production "orkestrasyon" fonksiyonunda birlestirmek. Roadmap M8.3'un
kendi "Olusturulacak Dosyalar" listesi YALNIZCA `ports/report_store_port.py`
ve `adapters/reporting/filesystem_report_store.py`'yi sayar; bu ucleyi
gercekten "uctan uca" baglamak, Roadmap'in ayrica ve acikca adlandirdigi
DAHA SONRAKI bir milestone'un isidir (Faz 9, M9.2 "Run Orchestrator (Uctan
Uca Kablo)"). Bu yuzden burada gorulen "compile -> store -> persist"
sirasi, bu testin kendisinde (gelecekteki Orchestrator'in rolunu oynayarak)
acikca yazilir - production kodunda degil.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from linkedinbot.adapters.reporting.filesystem_report_store import FilesystemReportStore
from linkedinbot.db.models import AccountOrm, RunLogOrm
from linkedinbot.db.repositories.report_repository import SqlAlchemyReportRepository
from linkedinbot.domain.evaluated_job import EvaluatedJob, JobStatus, MatchRationaleItem
from linkedinbot.domain.job_posting import JobPosting, WorkplaceType
from linkedinbot.domain.report import Report
from linkedinbot.domain.run_log import RunStatus, TriggerType
from linkedinbot.ports.job_repository_port import JobRepositoryPort
from linkedinbot.reporting.compiler import compile_report
from linkedinbot.scoring.company_scoring import CompanyScore

NOW = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)


class _FakeJobRepository(JobRepositoryPort):
    def __init__(self, job_postings: dict[str, JobPosting]):
        self._job_postings = job_postings

    def create(self, job_posting, content_hash):
        raise NotImplementedError

    def get_by_id(self, job_id: str) -> JobPosting | None:
        return self._job_postings.get(job_id)

    def update(self, job_posting, content_hash):
        raise NotImplementedError


def _run_log(account: AccountOrm) -> RunLogOrm:
    return RunLogOrm(
        account_id=account.account_id,
        trigger_type=TriggerType.MANUAL,
        started_at=NOW,
        ended_at=NOW,
        status=RunStatus.SUCCESS,
    )


def _evaluated_job(account_id, job_id: str) -> EvaluatedJob:
    rationale = [
        MatchRationaleItem(component="c", value="v", explanation="Matches preferred department."),
        MatchRationaleItem(component="c", value="v", explanation="Matches experience level."),
        MatchRationaleItem(component="c", value="v", explanation="Located in Istanbul."),
    ]
    return EvaluatedJob(
        account_id=account_id,
        job_id=job_id,
        company_id="Acme Corp",
        ai_match_score=90.0,
        match_rationale=rationale,
        department_cluster="Sales",
        status=JobStatus.NEW,
        first_seen_at=NOW,
        last_seen_at=NOW,
        content_hash_at_evaluation=f"hash-{job_id}",
        config_version_used=1,
    )


def _job_posting(job_id: str) -> JobPosting:
    return JobPosting(
        job_id=job_id,
        title="Business Development Executive",
        company_id="Acme Corp",
        location="Istanbul, Turkey",
        posted_date=NOW,
        description="Managing key accounts.",
        application_url=f"https://www.linkedin.com/jobs/view/{job_id}",
        collected_at=NOW,
        workplace_type=WorkplaceType.HYBRID,
        easy_apply=True,
    )


def _compile_and_persist(
    *,
    account_id,
    job_id: str,
    report_store: FilesystemReportStore,
    report_repository: SqlAlchemyReportRepository,
    run_id,
    config_snapshot_ref: int,
) -> Report:
    evaluated_job = _evaluated_job(account_id, job_id)
    job_repository = _FakeJobRepository({job_id: _job_posting(job_id)})
    company_scores = {
        "Acme Corp": CompanyScore(
            company_id="Acme Corp",
            weight_profile_id=None,
            rubric_version=1,
            score_total=85.0,
            score_breakdown={},
            evaluated_at=NOW,
        )
    }

    content = compile_report(
        [evaluated_job],
        job_repository,
        company_scores,
        top_n=10,
        run_date=date(2026, 8, 10),
        is_bootstrap=False,
    )

    report_id = uuid4()
    storage_path = report_store.save(account_id, report_id, NOW, content)

    report = Report(
        report_id=report_id,
        account_id=account_id,
        run_id=run_id,
        generated_at=NOW,
        included_job_ids=[job_id],
        top_matches=[job_id],
        config_snapshot_ref=config_snapshot_ref,
        storage_path=storage_path,
    )
    return report_repository.create(report)


def test_two_consecutive_compiles_produce_two_separate_files_and_two_separate_db_rows(
    db_session: Session, account: AccountOrm, make_config_profile, tmp_path: Path
):
    db_session.add(make_config_profile(account.account_id, config_version=1))
    db_session.add(make_config_profile(account.account_id, config_version=2, is_active=False))
    run_log_1 = _run_log(account)
    run_log_2 = _run_log(account)
    db_session.add(run_log_1)
    db_session.add(run_log_2)
    db_session.flush()

    report_store = FilesystemReportStore(base_dir=tmp_path)
    report_repository = SqlAlchemyReportRepository(db_session)

    first_report = _compile_and_persist(
        account_id=account.account_id,
        job_id="job-1",
        report_store=report_store,
        report_repository=report_repository,
        run_id=run_log_1.run_id,
        config_snapshot_ref=1,
    )
    second_report = _compile_and_persist(
        account_id=account.account_id,
        job_id="job-2",
        report_store=report_store,
        report_repository=report_repository,
        run_id=run_log_2.run_id,
        config_snapshot_ref=2,
    )

    # Iki ayri dosya.
    assert first_report.storage_path != second_report.storage_path
    assert Path(first_report.storage_path).exists()
    assert Path(second_report.storage_path).exists()
    assert "job-1" in Path(first_report.storage_path).read_text(encoding="utf-8")
    assert "job-2" in Path(second_report.storage_path).read_text(encoding="utf-8")

    # Iki ayri `reports` satiri, dogru (birbirinden bagimsiz, karismamis)
    # config_snapshot_ref degerleriyle - kasitli olarak FARKLI degerler
    # (1 ve 2) kullanilir, boylece bu assertion'lar yalnizca paylasilan
    # bir sabitin varligini degil, HER satirin KENDI degerini dogru
    # tasidigini kanitlar.
    fetched_1 = report_repository.get_by_id(account.account_id, first_report.report_id)
    fetched_2 = report_repository.get_by_id(account.account_id, second_report.report_id)
    assert fetched_1 is not None
    assert fetched_2 is not None
    assert fetched_1.report_id != fetched_2.report_id
    assert fetched_1.run_id == run_log_1.run_id
    assert fetched_2.run_id == run_log_2.run_id
    assert fetched_1.config_snapshot_ref == 1
    assert fetched_2.config_snapshot_ref == 2
