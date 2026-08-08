"""CompanyRepositoryPort - companies tablosu icin soyut arayuz.

companies bir Shared/Reference tablodur (PRD Section 15.0, TDD Section
14): gercek dunyadaki sirkete aittir, bir hesaba degil - JobRepositoryPort
ile ayni gerekce geregi account_id parametresi almaz.

`first_seen_at`/`last_updated_at` (companies tablosunda) neden domain
modelinde yok: CompanyProfile'in kendi `last_evaluated_timestamp` alani
bunlarla isim/anlam olarak orgusmuyor - CompanyProfile'in modul dokumani
zaten skorlamayla ilgili her seyin (Company Quality Score, Score
Breakdown, ve orada kalan bu zaman damgasinin) TDD'nin duzeltilmis
mimarisinde `company_scores`'a (M7.1, henuz domain modeli yok)
tasindigini belirtir. `first_seen_at`/`last_updated_at` ise gercekte
"bu sirket kaydi ilk ne zaman goruldu / en son ne zaman guncellendi"
turunden standart bir denetim (audit) zaman damgasi ciftidir - is
kurallarinin bir parcasi degil, kalicilik detayidir; bu yuzden cagirandan
gizlenmez ama domain modeline de eklenmez, repository tarafindan
otomatik yonetilir (create'de ikisi de "simdi", update'te yalnizca
last_updated_at yenilenir).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from linkedinbot.domain.company_profile import CompanyProfile


class CompanyRepositoryPort(ABC):
    """companies tablosu icin temel create/read/update islemleri (Roadmap M1.3)."""

    @abstractmethod
    def create(self, company: CompanyProfile) -> CompanyProfile:
        """Yeni bir sirket satiri olusturur."""

    @abstractmethod
    def get_by_id(self, company_id: str) -> CompanyProfile | None:
        """Sirket bulunamazsa None doner (Section 12.3 "Unrated" durumuyla
        karistirilmamalidir - o durum bir CompanyScore kaydinin skorsuz
        olmasidir, bu Port'un `None`'i ise sirketin hic kaydedilmemis
        olmasidir).
        """

    @abstractmethod
    def update(self, company: CompanyProfile) -> CompanyProfile:
        """Var olan bir sirket satirini gunceller."""
