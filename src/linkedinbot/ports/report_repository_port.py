"""ReportRepositoryPort - reports tablosu icin soyut arayuz.

Kasitli olarak `update()` metodu YOKTUR: FR-17 raporlarin "kalici, uzerine
yazilmayan" oldugunu acikca gerektirir - her calistirma kendi Report
satirini/dosyasini uretir, var olan bir raporu asla degistirmez. Bu
Port'un arayuzu bu kisitlamayi kod seviyesinde de yansitir (mumkun
olmayan bir islemi tanimlamamak, sonradan yanlislikla cagrilmasindan
daha guvenlidir).

`get_by_id`/`get_by_run_id` icin `account_id` zorunlulugu (M1.3 review
duzeltmesi): `reports`, TDD Section 14'un acikca Account-Scoped olarak
listeledigi bir tablodur ve Section 14 "bu tablolarin repository
katmanindaki hicbir sorgu metodu account_id parametresi olmadan
cagrilamaz (imza seviyesinde zorunlu)" der - Roadmap M1.3'un kendi
Tamamlanma Dogrulamasi da aynen bunu ister. Ilk implementasyon bu iki
metodu yalnizca surrogate ID ile sorguluyordu (account_id olmadan);
bu, hicbir yapisal engel olmadan baska bir hesabin raporunun UUID
tahmin/sizinti yoluyla okunabilmesi anlamina gelirdi. Duzeltme:
`account_id` her iki metoda da zorunlu parametre olarak eklendi;
eslesen satir baska bir hesaba aitse (account_id uyusmazsa) `None`
doner - bir hata degil, "bu hesap icin boyle bir kayit yok" anlamina
gelir (raporun BASKA bir hesapta var olup olmadigi cagirana asla
sizdirilmaz).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from linkedinbot.domain.report import Report


class ReportRepositoryPort(ABC):
    """reports tablosu icin temel create/read islemleri (Roadmap M1.3)."""

    @abstractmethod
    def create(self, report: Report) -> Report:
        """Yeni bir rapor satiri olusturur."""

    @abstractmethod
    def get_by_id(self, account_id: UUID, report_id: UUID) -> Report | None:
        """Rapor bulunamazsa VEYA baska bir hesaba aitse None doner."""

    @abstractmethod
    def get_by_run_id(self, account_id: UUID, run_id: UUID) -> Report | None:
        """TDD Section 16 (v1.1) run_logs (1)->(1) reports iliskisini ve
        Section 18'in idempotency kontrolunu ("bu run_id icin daha once
        bir reports satiri var mi") destekler. Rapor bulunamazsa VEYA
        baska bir hesaba aitse None doner.
        """
