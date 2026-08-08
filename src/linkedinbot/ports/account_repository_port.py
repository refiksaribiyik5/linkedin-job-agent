"""AccountRepositoryPort - accounts tablosu icin soyut arayuz (TDD Section 3
Karar 2, Section 6 `db.repositories.*` satiri).

Bu Port, `linkedinbot.domain.account.Account` disinda hicbir tipe bagimli
degildir; somut implementasyonu (SQLAlchemy, vb.) `db/repositories/`
altindadir. Domain/Application katmanlari her zaman bu soyut arayuza
bagimli olmalidir, somut implementasyona degil (TDD Section 3 "Bagimlilik
yonu": Adapters -> Application -> Domain).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from linkedinbot.domain.account import Account


class AccountRepositoryPort(ABC):
    """accounts tablosu icin temel create/read/update islemleri (Roadmap M1.3)."""

    @abstractmethod
    def create(self, account: Account) -> Account:
        """Yeni bir hesap satiri olusturur. `account.account_id` None
        olabilir (henuz kalici degil) - donen nesnenin `account_id`'si
        her zaman doludur (DB tarafindan uretilmis olabilir).
        """

    @abstractmethod
    def get_by_id(self, account_id: UUID) -> Account | None:
        """Hesap bulunamazsa None doner (sessiz bir varsayilan uretmez)."""

    @abstractmethod
    def update(self, account: Account) -> Account:
        """`account.account_id` dolu olmalidir (var olan bir satiri gunceller)."""
