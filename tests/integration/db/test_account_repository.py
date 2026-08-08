"""SqlAlchemyAccountRepository icin entegrasyon testleri (Roadmap M1.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from linkedinbot.db.repositories.account_repository import SqlAlchemyAccountRepository
from linkedinbot.domain.account import Account
from linkedinbot.ports.account_repository_port import AccountRepositoryPort

NOW = datetime(2026, 8, 8, tzinfo=UTC)


def test_repository_implements_port(db_session: Session):
    repo = SqlAlchemyAccountRepository(db_session)
    assert isinstance(repo, AccountRepositoryPort)


def test_create_populates_account_id(db_session: Session):
    repo = SqlAlchemyAccountRepository(db_session)
    created = repo.create(Account(display_name="Test Hesabi", created_at=NOW, status="active"))
    assert created.account_id is not None
    assert created.display_name == "Test Hesabi"
    assert created.status == "active"
    assert created.next_run_at is None


def test_get_by_id_returns_none_when_not_found(db_session: Session):
    repo = SqlAlchemyAccountRepository(db_session)
    assert repo.get_by_id(uuid4()) is None


def test_get_by_id_returns_created_account(db_session: Session):
    repo = SqlAlchemyAccountRepository(db_session)
    created = repo.create(Account(display_name="Test Hesabi", created_at=NOW, status="active"))

    fetched = repo.get_by_id(created.account_id)

    assert fetched is not None
    assert fetched.account_id == created.account_id
    assert fetched.display_name == "Test Hesabi"
    assert fetched.status == "active"


def test_update_changes_status_and_next_run_at(db_session: Session):
    repo = SqlAlchemyAccountRepository(db_session)
    created = repo.create(Account(display_name="Test Hesabi", created_at=NOW, status="active"))

    updated = repo.update(
        created.model_copy(update={"status": "paused", "next_run_at": NOW})
    )

    assert updated.status == "paused"
    assert updated.next_run_at == NOW
    refetched = repo.get_by_id(created.account_id)
    assert refetched.status == "paused"


def test_update_without_account_id_raises_value_error(db_session: Session):
    repo = SqlAlchemyAccountRepository(db_session)
    with pytest.raises(ValueError, match="account_id"):
        repo.update(Account(display_name="Test Hesabi", created_at=NOW, status="active"))


def test_update_unknown_account_id_raises_value_error(db_session: Session):
    repo = SqlAlchemyAccountRepository(db_session)
    unknown = Account(
        account_id=uuid4(), display_name="Ghost", created_at=NOW, status="active"
    )
    with pytest.raises(ValueError, match="bulunamadi"):
        repo.update(unknown)
