"""Job Posting - ham/toplanan ilan verisi (PRD Section 15.2).

Bu bir Shared/Reference varligidir (PRD Section 15.0): bir hesaba degil,
gercek dunyadaki ilana aittir ve hesaplar arasi paylasilabilir. Bu modul
saf veri sekli tanimlar; toplama (Playwright), normalizasyon (content hash)
ve kalicilik (SQLAlchemy) sonraki milestone'larin (M3.1, M4.1, M1.2) isidir.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, HttpUrl


class WorkplaceType(StrEnum):
    """PRD Section 15.2: Workplace Type | On-site / Hybrid / Remote."""

    ON_SITE = "On-site"
    HYBRID = "Hybrid"
    REMOTE = "Remote"


class JobPosting(BaseModel):
    """PRD Section 15.2 - Job Posting (Ham / Toplanan Veri).

    Zorunlu alanlar FR-2'nin "gerekli minimum alanlar" listesiyle
    (baslik, sirket, lokasyon, tarih, aciklama, link) esler; FR-2'de acikca
    listelenmeyen alanlar (workplace_type, employment_type, easy_apply)
    LinkedIn'de her zaman mevcut olmayabileceginden opsiyoneldir.
    """

    job_id: str
    title: str
    company_id: str
    location: str
    posted_date: datetime
    description: str
    application_url: HttpUrl
    collected_at: datetime

    workplace_type: WorkplaceType | None = None
    employment_type: str | None = None
    easy_apply: bool | None = None
