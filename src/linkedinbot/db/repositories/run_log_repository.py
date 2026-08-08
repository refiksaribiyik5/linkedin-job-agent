"""SqlAlchemyRunLogRepository - RunLogRepositoryPort'un SQLAlchemy uygulamasi."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from linkedinbot.db.models import RunLogOrm
from linkedinbot.domain.run_log import RunLog
from linkedinbot.ports.run_log_repository_port import RunLogRepositoryPort


def _to_domain(orm_run_log: RunLogOrm) -> RunLog:
    return RunLog(
        run_id=orm_run_log.run_id,
        account_id=orm_run_log.account_id,
        trigger_type=orm_run_log.trigger_type,
        started_at=orm_run_log.started_at,
        ended_at=orm_run_log.ended_at,
        jobs_collected=orm_run_log.jobs_collected,
        jobs_filtered=orm_run_log.jobs_filtered,
        jobs_new=orm_run_log.jobs_new,
        jobs_closed=orm_run_log.jobs_closed,
        status=orm_run_log.status,
        error_detail=orm_run_log.error_detail,
        collection_capped=orm_run_log.collection_capped,
    )


class SqlAlchemyRunLogRepository(RunLogRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, run_log: RunLog) -> RunLog:
        if run_log.ended_at is None:
            raise ValueError(
                "run_logs satiri yalnizca calistirma sonlandiktan sonra yazilir "
                "(TDD Section 17); ended_at None olamaz."
            )
        orm_run_log = RunLogOrm(
            run_id=run_log.run_id,
            account_id=run_log.account_id,
            trigger_type=run_log.trigger_type,
            started_at=run_log.started_at,
            ended_at=run_log.ended_at,
            jobs_collected=run_log.jobs_collected,
            jobs_filtered=run_log.jobs_filtered,
            jobs_new=run_log.jobs_new,
            jobs_closed=run_log.jobs_closed,
            status=run_log.status,
            error_detail=run_log.error_detail,
            collection_capped=run_log.collection_capped,
        )
        self._session.add(orm_run_log)
        self._session.flush()
        return _to_domain(orm_run_log)

    def get_by_id(self, run_id: UUID) -> RunLog | None:
        orm_run_log = self._session.get(RunLogOrm, run_id)
        return _to_domain(orm_run_log) if orm_run_log is not None else None
