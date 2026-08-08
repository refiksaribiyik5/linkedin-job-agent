"""Evaluated Job - skorlanmis kayit (PRD Section 15.4).

Bu bir Account-Scoped varliktir (PRD Section 15.0): Job Posting ve Company
Profile'in aksine, belirli bir hesaba baglidir ve hesaplar arasi
paylasilmaz. Job Posting Reference / Company Profile Reference alanlari,
Section 15.0'in "Shared/Reference" ilkesiyle tutarli olarak birer kimlik
(job_id / company_id) referansidir; ilgili varligin tam kopyasi degildir.

Status enum'u ve is_borderline alani icin: PRD 15.4 dort durum listeler
(New/Seen/Updated/Closed); TDD Section 15'teki semada ayrica Borderline ve
Excluded de ENUM'a dahil edilmisti, ancak TDD Section 17 ("Durum Yonetimi")
Borderline'in durum enum'unun bir kolu degil, ayri bir boolean bayrak
(is_borderline) olmasi gerektigini acikca belirtir. Bu modul Section 17'nin
bu daha ayrintili/gerekceli cozumunu esas alir: JobStatus be seviyeli
kalir (New/Seen/Updated/Closed/Excluded) ve is_borderline ayri bir alandir.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class JobStatus(StrEnum):
    """PRD Section 15.4 + FR-19 (Excluded); Borderline TDD Section 17 geregi
    ayri bir alandir (bkz. EvaluatedJob.is_borderline), enum'a dahil degildir.
    """

    NEW = "New"
    SEEN = "Seen"
    UPDATED = "Updated"
    CLOSED = "Closed"
    EXCLUDED = "Excluded"


class FilterResult(BaseModel):
    """TDD Section 11: her filtre bir FilterResult doner (yalnizca boolean
    degil) - {passed, reason, confidence}. EvaluatedJob.filter_result_detail
    alaninin dogrudan kaynagidir (acilanabilirlik, G-3).
    """

    passed: bool
    reason: str
    confidence: float | None = Field(default=None, ge=0, le=1)


class MatchRationaleItem(BaseModel):
    """TDD Section 10 grounding semasi: her gerekce maddesi {component,
    value, explanation} seklinde yapilandirilmistir (RISK-10 mitigasyonu -
    serbest, dogrulanamayan LLM yorumu degil, yapisal skor bilesenlerine
    dayanir).
    """

    component: str
    value: str
    explanation: str


class EvaluatedJob(BaseModel):
    """PRD Section 15.4 - Evaluated Job (Skorlanmis Kayit).

    account_id, PRD Section 15.0'in "Evaluated Job'in kullaniciya ozgu
    kismi ... Account-Scoped" ilkesinin dogrudan sonucudur.

    AI Match Score / Match Rationale iliskisi FR-7 geregi ayristirilamaz:
    "her ilan ... bir AI Match Score alir ve skora eslik eden bir gerekce
    listesi uretilir" - skor varsa gerekce de vardir (en az 3 madde),
    gerekce varsa skor da vardir.
    """

    account_id: UUID
    job_id: str
    company_id: str

    ai_match_score: float | None = Field(default=None, ge=0, le=100)
    match_rationale: list[MatchRationaleItem] | None = None
    department_cluster: str | None = None
    filter_result_detail: dict[str, FilterResult] | None = None

    status: JobStatus
    is_borderline: bool = False

    first_seen_at: datetime
    last_seen_at: datetime
    report_appearances_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _score_and_rationale_travel_together(self) -> EvaluatedJob:
        has_score = self.ai_match_score is not None
        has_rationale = bool(self.match_rationale)
        if has_score != has_rationale:
            raise ValueError(
                "ai_match_score ve match_rationale FR-7 geregi birlikte "
                "bulunur veya birlikte bulunmaz (skor gerekcesiz sunulmaz)."
            )
        if has_rationale and len(self.match_rationale) < 3:
            raise ValueError(
                "match_rationale FR-7 kabul kriteri geregi en az 3 madde icermelidir."
            )
        return self
