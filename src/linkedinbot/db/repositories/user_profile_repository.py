"""SqlAlchemyUserProfileRepository - UserProfileRepositoryPort'un SQLAlchemy uygulamasi."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from linkedinbot.db.models import UserProfileOrm
from linkedinbot.domain.user_profile import Preferences, UserProfile
from linkedinbot.ports.user_profile_repository_port import UserProfileRepositoryPort


def _to_domain(orm_profile: UserProfileOrm) -> UserProfile:
    return UserProfile(
        career_goals=orm_profile.career_goals,
        skills_summary=orm_profile.skills_summary,
        preferences=Preferences(**orm_profile.preferences_dealbreakers),
    )


class SqlAlchemyUserProfileRepository(UserProfileRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, account_id: UUID, user_profile: UserProfile) -> UserProfile:
        orm_profile = UserProfileOrm(
            account_id=account_id,
            career_goals=user_profile.career_goals,
            skills_summary=user_profile.skills_summary,
            preferences_dealbreakers=user_profile.preferences.model_dump(mode="json"),
        )
        self._session.add(orm_profile)
        self._session.flush()
        return _to_domain(orm_profile)

    def get_by_account_id(self, account_id: UUID) -> UserProfile | None:
        orm_profile = self._session.get(UserProfileOrm, account_id)
        return _to_domain(orm_profile) if orm_profile is not None else None

    def update(self, account_id: UUID, user_profile: UserProfile) -> UserProfile:
        orm_profile = self._session.get(UserProfileOrm, account_id)
        if orm_profile is None:
            raise ValueError(f"Guncellenecek profil bulunamadi: {account_id}")
        orm_profile.career_goals = user_profile.career_goals
        orm_profile.skills_summary = user_profile.skills_summary
        orm_profile.preferences_dealbreakers = user_profile.preferences.model_dump(mode="json")
        self._session.flush()
        return _to_domain(orm_profile)
