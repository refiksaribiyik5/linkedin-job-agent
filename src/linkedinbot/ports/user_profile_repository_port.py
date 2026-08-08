"""UserProfileRepositoryPort - user_profiles tablosu icin soyut arayuz.

user_profiles, account_id'yi kendi PK'si olarak kullanir (1:1 iliski,
surrogate anahtar yoktur - bkz. db/models.py UserProfileOrm). UserProfile
domain modeli (M1.1) kasitli olarak account_id tasimaz (bkz.
domain/account_context.py: AccountContext = account_id + user_profile,
normalize edilmis kompozisyon); bu yuzden account_id burada gizli bir
kalicilik detayi olarak degil, zaten var olan bir domain kompozisyon
deseninin (AccountContext) dogal bir parcasi olarak acik parametre
gecilir - TDD Section 14'un "account_id parametresi olmadan hicbir
Account-Scoped sorgu metodu cagirilamaz" kuralini imza seviyesinde de
zorunlu kilar.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from linkedinbot.domain.user_profile import UserProfile


class UserProfileRepositoryPort(ABC):
    """user_profiles tablosu icin temel create/read/update islemleri (Roadmap M1.3)."""

    @abstractmethod
    def create(self, account_id: UUID, user_profile: UserProfile) -> UserProfile:
        """Verilen hesap icin bir user_profiles satiri olusturur."""

    @abstractmethod
    def get_by_account_id(self, account_id: UUID) -> UserProfile | None:
        """Profil bulunamazsa None doner."""

    @abstractmethod
    def update(self, account_id: UUID, user_profile: UserProfile) -> UserProfile:
        """Var olan bir user_profiles satirini gunceller."""
