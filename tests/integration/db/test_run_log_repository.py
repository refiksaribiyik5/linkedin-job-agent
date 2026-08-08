"""SqlAlchemyRunLogRepository icin entegrasyon testleri (Roadmap M1.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from linkedinbot.db.models import AccountOrm
from linkedinbot.db.repositories.run_log_repository import SqlAlchemyRunLogRepository
from linkedinbot.domain.run_log import RunLog, RunStatus, TriggerType
from linkedinbot.ports.run_log_repository_port import RunLogRepositoryPort

NOW = datetime(2026, 8, 8, tzinfo=UTC)


def test_repository_implements_port(db_session: Session):
    repo = SqlAlchemyRunLogRepository(db_session)
    assert isinstance(repo, RunLogRepositoryPort)


def test_create_and_get_by_id_round_trip(db_session: Session, account: AccountOrm):
    repo = SqlAlchemyRunLogRepository(db_session)
    run_log = RunLog(
        run_id=uuid4(),
        account_id=account.account_id,
        trigger_type=TriggerType.SCHEDULED,
        started_at=NOW,
        ended_at=NOW,
        jobs_collected=10,
        jobs_filtered=4,
        jobs_new=2,
        jobs_closed=1,
        status=RunStatus.SUCCESS,
    )

    created = repo.create(run_log)
    fetched = repo.get_by_id(account.account_id, created.run_id)

    assert fetched is not None
    assert fetched.jobs_collected == 10
    assert fetched.status == RunStatus.SUCCESS


def test_get_by_id_returns_none_for_run_log_belonging_to_a_different_account(
    db_session: Session, account: AccountOrm
):
    # Review duzeltmesi (BLOCKER-1, TDD Section 14): get_by_id account_id
    # olmadan cagirilamaz VE yanlis hesapla cagirildiginda None doner.
    repo = SqlAlchemyRunLogRepository(db_session)
    run_log = repo.create(
        RunLog(
            run_id=uuid4(),
            account_id=account.account_id,
            trigger_type=TriggerType.SCHEDULED,
            started_at=NOW,
            ended_at=NOW,
            status=RunStatus.SUCCESS,
        )
    )

    other_account_id = uuid4()

    assert repo.get_by_id(other_account_id, run_log.run_id) is None


def test_create_with_ended_at_none_raises_value_error(db_session: Session, account: AccountOrm):
    # TDD Section 17: bir run_logs satiri yalnizca calistirma sonlandiktan
    # sonra var olur; ended_at=None bir RunLog'un henuz terminal durumda
    # olmadigi anlamina gelir ve bu yuzden hic kalici hale getirilmemelidir.
    repo = SqlAlchemyRunLogRepository(db_session)
    in_progress = RunLog(
        run_id=uuid4(),
        account_id=account.account_id,
        trigger_type=TriggerType.MANUAL,
        started_at=NOW,
        ended_at=None,
        status=RunStatus.SUCCESS,
    )
    with pytest.raises(ValueError, match="ended_at"):
        repo.create(in_progress)


def test_get_by_id_returns_none_when_not_found(db_session: Session, account: AccountOrm):
    repo = SqlAlchemyRunLogRepository(db_session)
    assert repo.get_by_id(account.account_id, uuid4()) is None


def test_create_failed_run_requires_error_detail_at_domain_level(
    db_session: Session, account: AccountOrm
):
    # M1.1'in RunLog validator'i (_failed_runs_are_never_silent, FR-15) bu
    # repository'nin altinda hala aktiftir - repository bunu tekrar
    # uygulamaz, domain modelinin kendisi zaten reddeder.
    with pytest.raises(ValidationError):
        RunLog(
            run_id=uuid4(),
            account_id=account.account_id,
            trigger_type=TriggerType.MANUAL,
            started_at=NOW,
            ended_at=NOW,
            status=RunStatus.FAILED,
            error_detail=None,
        )
