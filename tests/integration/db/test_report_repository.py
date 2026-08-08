"""SqlAlchemyReportRepository icin entegrasyon testleri (Roadmap M1.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from linkedinbot.db.models import AccountOrm, RunLogOrm
from linkedinbot.db.repositories.report_repository import SqlAlchemyReportRepository
from linkedinbot.domain.report import Report
from linkedinbot.domain.run_log import RunStatus, TriggerType
from linkedinbot.ports.report_repository_port import ReportRepositoryPort

NOW = datetime(2026, 8, 8, tzinfo=UTC)


def _run_log(account: AccountOrm) -> RunLogOrm:
    return RunLogOrm(
        account_id=account.account_id,
        trigger_type=TriggerType.MANUAL,
        started_at=NOW,
        ended_at=NOW,
        status=RunStatus.SUCCESS,
    )


def test_repository_implements_port(db_session: Session):
    repo = SqlAlchemyReportRepository(db_session)
    assert isinstance(repo, ReportRepositoryPort)


def test_create_and_get_by_id_round_trip(
    db_session: Session, account: AccountOrm, make_config_profile
):
    db_session.add(make_config_profile(account.account_id))
    run_log = _run_log(account)
    db_session.add(run_log)
    db_session.flush()
    repo = SqlAlchemyReportRepository(db_session)

    report = Report(
        report_id=uuid4(),
        account_id=account.account_id,
        run_id=run_log.run_id,
        generated_at=NOW,
        included_job_ids=["linkedin-1", "linkedin-2"],
        top_matches=["linkedin-1"],
        config_snapshot_ref=1,
        storage_path=Path(f"reports/{account.account_id}/report.md"),
    )

    created = repo.create(report)
    fetched = repo.get_by_id(created.report_id)

    assert fetched is not None
    assert fetched.run_id == run_log.run_id
    assert fetched.included_job_ids == ["linkedin-1", "linkedin-2"]
    assert fetched.format == "Markdown"
    assert isinstance(fetched.storage_path, Path)


def test_get_by_id_returns_none_when_not_found(db_session: Session):
    repo = SqlAlchemyReportRepository(db_session)
    assert repo.get_by_id(uuid4()) is None


def test_get_by_run_id_returns_matching_report(
    db_session: Session, account: AccountOrm, make_config_profile
):
    db_session.add(make_config_profile(account.account_id))
    run_log = _run_log(account)
    db_session.add(run_log)
    db_session.flush()
    repo = SqlAlchemyReportRepository(db_session)
    repo.create(
        Report(
            report_id=uuid4(),
            account_id=account.account_id,
            run_id=run_log.run_id,
            generated_at=NOW,
            config_snapshot_ref=1,
            storage_path=Path("reports/x.md"),
        )
    )

    fetched = repo.get_by_run_id(run_log.run_id)

    assert fetched is not None
    assert fetched.run_id == run_log.run_id


def test_get_by_run_id_returns_none_when_not_found(db_session: Session):
    repo = SqlAlchemyReportRepository(db_session)
    assert repo.get_by_run_id(uuid4()) is None
