"""RunLogRepositoryPort - run_logs tablosu icin soyut arayuz.

Kasitli olarak `update()` metodu YOKTUR: TDD Section 17'nin atomiklik
stratejisi geregi bir run_logs satiri yalnizca bir calistirma
sonlandiktan SONRA, tek bir atomik transaction icinde yazilir - var olan
bir kayit daha sonra degistirilmez (kalici bir tarihsel kayittir, NFR-11
"asla silme" ilkesinin dogal bir uzantisidir).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from linkedinbot.domain.run_log import RunLog


class RunLogRepositoryPort(ABC):
    """run_logs tablosu icin temel create/read islemleri (Roadmap M1.3)."""

    @abstractmethod
    def create(self, run_log: RunLog) -> RunLog:
        """Yeni bir calistirma kaydi olusturur. `run_log.ended_at` None
        olamaz - bir RunLog satiri yalnizca calistirma sonlandiktan sonra
        var olur (bkz. db/models.py RunLogOrm dokumani); bu kural
        implementasyon tarafinda zorunlu kilinir.
        """

    @abstractmethod
    def get_by_id(self, run_id: UUID) -> RunLog | None:
        """Kayit bulunamazsa None doner."""
