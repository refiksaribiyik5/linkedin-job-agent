"""ReportRepositoryPort - reports tablosu icin soyut arayuz.

Kasitli olarak `update()` metodu YOKTUR: FR-17 raporlarin "kalici, uzerine
yazilmayan" oldugunu acikca gerektirir - her calistirma kendi Report
satirini/dosyasini uretir, var olan bir raporu asla degistirmez. Bu
Port'un arayuzu bu kisitlamayi kod seviyesinde de yansitir (mumkun
olmayan bir islemi tanimlamamak, sonradan yanlislikla cagrilmasindan
daha guvenlidir).
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
    def get_by_id(self, report_id: UUID) -> Report | None:
        """Rapor bulunamazsa None doner."""

    @abstractmethod
    def get_by_run_id(self, run_id: UUID) -> Report | None:
        """TDD Section 16 (v1.1) run_logs (1)->(1) reports iliskisini ve
        Section 18'in idempotency kontrolunu ("bu run_id icin daha once
        bir reports satiri var mi") destekler.
        """
