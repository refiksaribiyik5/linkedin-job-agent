"""Run Log - calistirma kaydi (PRD Section 15.6).

Bu bir Account-Scoped varliktir (PRD Section 15.0). Status alani icin PRD
15.6 ve TDD Section 15 semasi birbiriyle tutarlidir (Success/Partial/
Failed, uc deger) - TDD Section 17'deki "Pending -> Running -> {Success,
Partial, Failed}" genis surec modeli, Orchestrator'in bellek-ici gecici
durumlaridir; bir RunLog kaydi yalnizca terminal durumda olusur/tamamlanir,
bu yuzden Pending/Running degerleri bu enum'a dahil degildir.

collection_capped, PRD 15.6'nin alan listesinde acikca yer almaz, ancak
FR-21'in kendisi Run Log'un bu bilgiyi tasimasini acikca ister ("... bu
durumu ... Run Log'da acikca belirtir").

`partial_reason` (Roadmap M1.1 duzeltmesi, M9.4 "Hata Siniflandirma +
Retry"): Section 21'in devre kesici (circuit-breaker-lite) mekanizmasi
bir calistirmayi 'Partial' isaretlerken, bu kararin gerekcesini tasiyacak
ayri bir alan yoktur. Mevcut `error_detail` alani bunun icin KULLANILMAZ:
PRD 15.6 bu alani acikca 'hata bilgisi' olarak tanimlar ve yalnizca
`Failed` durumunda zorunludur (bkz. `_failed_runs_are_never_silent`);
Partial bir calistirma bir hata DEGILDIR - Section 15.7 Partial'i Success
ile AYNI sekilde her zaman bir rapor ureten, tam teskkullu bir sonuc
olarak tanimlar. `error_detail`'in Partial icin yeniden kullanilmasi bu
ayrimi bulaniklastirirdi. `partial_reason`, `status == Partial` iken
ZORUNLU, aksi durumda KULLANILMAYAN (bos birakilmasi gereken) bir
alandir - `error_detail`/`Failed` simetrisinin aynisi.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class TriggerType(StrEnum):
    """PRD Section 15.6: Trigger Type | Scheduled / Manual."""

    SCHEDULED = "Scheduled"
    MANUAL = "Manual"


class RunStatus(StrEnum):
    """PRD Section 15.6: Status | Success / Partial / Failed."""

    SUCCESS = "Success"
    PARTIAL = "Partial"
    FAILED = "Failed"


class RunLog(BaseModel):
    """PRD Section 15.6 - Run Log (Execution History)."""

    run_id: UUID
    account_id: UUID
    trigger_type: TriggerType

    started_at: datetime
    ended_at: datetime | None = None

    jobs_collected: int = Field(default=0, ge=0)
    jobs_filtered: int = Field(default=0, ge=0)
    jobs_new: int = Field(default=0, ge=0)
    jobs_closed: int = Field(default=0, ge=0)

    status: RunStatus
    error_detail: str | None = None
    partial_reason: str | None = None
    collection_capped: bool = False

    @model_validator(mode="after")
    def _failed_runs_are_never_silent(self) -> RunLog:
        # FR-15: "Bir calistirma basarisiz olursa ... sessiz hata olusmaz."
        if self.status == RunStatus.FAILED and not self.error_detail:
            raise ValueError(
                "status Failed ise error_detail FR-15 geregi bos birakilamaz "
                "(sessiz hata olusmamalidir)."
            )
        return self

    @model_validator(mode="after")
    def _partial_reason_matches_partial_status(self) -> RunLog:
        # M9.4: partial_reason, error_detail/Failed ile AYNI simetride -
        # status Partial iken zorunlu, aksi durumda kullanilmaz.
        if self.status == RunStatus.PARTIAL and not self.partial_reason:
            raise ValueError(
                "status Partial ise partial_reason zorunludur (devre kesicinin "
                "neden tetiklendigi acikca belirtilmelidir)."
            )
        if self.status != RunStatus.PARTIAL and self.partial_reason:
            raise ValueError(
                "partial_reason yalnizca status Partial iken kullanilir; "
                "diger durumlarda bos birakilmalidir."
            )
        return self
