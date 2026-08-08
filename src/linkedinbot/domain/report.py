"""Report - uretilen rapor kaydi (PRD Section 15.5).

Bu bir Account-Scoped varliktir (PRD Section 15.0). top_matches icin
kasitli olarak bir uzunluk sinirlamasi (orn. en fazla 10) uygulanmaz:
Section 17 "Top Matches Sayisi" degerini acikca konfigure edilebilir bir
parametre olarak tanimlar (varsayilan 10, degistirilebilir); bu sayiyi
domain modeline sabit bir kural olarak gommek NFR-6/Config-Is Mantigi
Ayrimi ilkesini ihlal eder. Sayimi uygulamak Ranking servisinin (M8.1)
sorumlulugudur.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field


class Report(BaseModel):
    """PRD Section 15.5 - Report.

    config_snapshot_ref, PRD'nin kendi tanimladigi gibi bir "referans
    bilgisi"dir (henuz M1.1'de tanimli olmayan bir Config Snapshot
    nesnesinin gomulu kopyasi degil - bkz. AccountContext modul dokumani).
    """

    report_id: UUID
    account_id: UUID
    generated_at: datetime

    included_job_ids: list[str] = Field(default_factory=list)
    top_matches: list[str] = Field(default_factory=list)

    format: str = "Markdown"
    config_snapshot_ref: str
    storage_path: Path
