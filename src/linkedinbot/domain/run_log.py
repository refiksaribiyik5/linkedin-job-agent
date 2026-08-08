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
