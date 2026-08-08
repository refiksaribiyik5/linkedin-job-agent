"""SqlAlchemyAccountRepository - AccountRepositoryPort'un SQLAlchemy uygulamasi.

TDD Section 3 "Bagimlilik yonu" (Adapters -> Application -> Domain) geregi,
bu modul hem `linkedinbot.ports` (uyguladigi soyut arayuz) hem
`linkedinbot.domain` (donusturdugu domain tipi) hem de `linkedinbot.db.models`
(somut ORM) katmanlarina bagimlidir - bu izin verilen tek yondur.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from linkedinbot.db.models import AccountOrm
from linkedinbot.domain.account import Account
from linkedinbot.ports.account_repository_port import AccountRepositoryPort


def _to_domain(orm_account: AccountOrm) -> Account:
    return Account(
        account_id=orm_account.account_id,
        display_name=orm_account.display_name,
        created_at=orm_account.created_at,
        status=orm_account.status,
        next_run_at=orm_account.next_run_at,
    )


class SqlAlchemyAccountRepository(AccountRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, account: Account) -> Account:
        orm_account = AccountOrm(
            display_name=account.display_name,
            created_at=account.created_at,
            status=account.status,
            next_run_at=account.next_run_at,
        )
        if account.account_id is not None:
            orm_account.account_id = account.account_id
        self._session.add(orm_account)
        self._session.flush()
        return _to_domain(orm_account)

    def get_by_id(self, account_id: UUID) -> Account | None:
        orm_account = self._session.get(AccountOrm, account_id)
        return _to_domain(orm_account) if orm_account is not None else None

    def update(self, account: Account) -> Account:
        if account.account_id is None:
            raise ValueError("update() icin account.account_id dolu olmalidir.")
        orm_account = self._session.get(AccountOrm, account.account_id)
        if orm_account is None:
            raise ValueError(f"Guncellenecek hesap bulunamadi: {account.account_id}")
        orm_account.display_name = account.display_name
        orm_account.status = account.status
        orm_account.next_run_at = account.next_run_at
        self._session.flush()
        return _to_domain(orm_account)
