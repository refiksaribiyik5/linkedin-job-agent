"""SqlAlchemyReportRepository - ReportRepositoryPort'un SQLAlchemy uygulamasi."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from linkedinbot.db.models import ReportOrm
from linkedinbot.domain.report import Report
from linkedinbot.ports.report_repository_port import ReportRepositoryPort


def _to_domain(orm_report: ReportOrm) -> Report:
    return Report(
        report_id=orm_report.report_id,
        account_id=orm_report.account_id,
        run_id=orm_report.run_id,
        generated_at=orm_report.generated_at,
        included_job_ids=orm_report.included_job_ids,
        top_matches=orm_report.top_matches,
        format=orm_report.format,
        config_snapshot_ref=orm_report.config_snapshot_ref,
        storage_path=orm_report.storage_path,
    )


class SqlAlchemyReportRepository(ReportRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, report: Report) -> Report:
        orm_report = ReportOrm(
            report_id=report.report_id,
            account_id=report.account_id,
            run_id=report.run_id,
            generated_at=report.generated_at,
            included_job_ids=report.included_job_ids,
            top_matches=report.top_matches,
            format=report.format,
            config_snapshot_ref=report.config_snapshot_ref,
            storage_path=str(report.storage_path),
        )
        self._session.add(orm_report)
        self._session.flush()
        return _to_domain(orm_report)

    def get_by_id(self, account_id: UUID, report_id: UUID) -> Report | None:
        orm_report = self._session.execute(
            select(ReportOrm).where(
                ReportOrm.report_id == report_id, ReportOrm.account_id == account_id
            )
        ).scalar_one_or_none()
        return _to_domain(orm_report) if orm_report is not None else None

    def get_by_run_id(self, account_id: UUID, run_id: UUID) -> Report | None:
        orm_report = self._session.execute(
            select(ReportOrm).where(
                ReportOrm.run_id == run_id, ReportOrm.account_id == account_id
            )
        ).scalar_one_or_none()
        return _to_domain(orm_report) if orm_report is not None else None
