"""SqlAlchemyUserProfileRepository icin entegrasyon testleri (Roadmap M1.3)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from linkedinbot.db.models import AccountOrm
from linkedinbot.db.repositories.user_profile_repository import SqlAlchemyUserProfileRepository
from linkedinbot.domain.user_profile import Preferences, UserProfile
from linkedinbot.ports.user_profile_repository_port import UserProfileRepositoryPort


def test_repository_implements_port(db_session: Session):
    repo = SqlAlchemyUserProfileRepository(db_session)
    assert isinstance(repo, UserProfileRepositoryPort)


def test_create_and_get_round_trip(db_session: Session, account: AccountOrm):
    repo = SqlAlchemyUserProfileRepository(db_session)
    profile = UserProfile(
        career_goals="Business Development",
        skills_summary="Satis, musteri iliskileri",
        preferences=Preferences(excluded_companies=["acme-corp"]),
    )

    created = repo.create(account.account_id, profile)
    fetched = repo.get_by_account_id(account.account_id)

    assert created.career_goals == "Business Development"
    assert fetched is not None
    assert fetched.skills_summary == "Satis, musteri iliskileri"
    assert fetched.preferences.excluded_companies == ["acme-corp"]


def test_get_by_account_id_returns_none_when_not_found(db_session: Session):
    repo = SqlAlchemyUserProfileRepository(db_session)
    assert repo.get_by_account_id(uuid4()) is None


def test_update_changes_career_goals(db_session: Session, account: AccountOrm):
    repo = SqlAlchemyUserProfileRepository(db_session)
    repo.create(
        account.account_id,
        UserProfile(career_goals="Old goal", skills_summary="Eski beceriler"),
    )

    updated = repo.update(
        account.account_id,
        UserProfile(career_goals="New goal", skills_summary="Yeni beceriler"),
    )

    assert updated.career_goals == "New goal"
    fetched = repo.get_by_account_id(account.account_id)
    assert fetched.career_goals == "New goal"


def test_update_unknown_account_id_raises_value_error(db_session: Session):
    repo = SqlAlchemyUserProfileRepository(db_session)
    with pytest.raises(ValueError, match="bulunamadi"):
        repo.update(
            uuid4(), UserProfile(career_goals="Goal", skills_summary="Beceriler")
        )
