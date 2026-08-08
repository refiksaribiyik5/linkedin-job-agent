"""Report - uretilen rapor kaydi (PRD Section 15.5).

Bu bir Account-Scoped varliktir (PRD Section 15.0). top_matches icin
kasitli olarak bir uzunluk sinirlamasi (orn. en fazla 10) uygulanmaz:
Section 17 "Top Matches Sayisi" degerini acikca konfigure edilebilir bir
parametre olarak tanimlar (varsayilan 10, degistirilebilir); bu sayiyi
domain modeline sabit bir kural olarak gommek NFR-6/Config-Is Mantigi
Ayrimi ilkesini ihlal eder. Sayimi uygulamak Ranking servisinin (M8.1)
sorumlulugudur.

`run_id`, `config_snapshot_ref` (M1.3 duzeltmesi): M1.1 zamaninda
`account_config_profiles` tablosu (ve onun `config_version` alani) henuz
somut degildi; bu yuzden `config_snapshot_ref` gecici olarak `str`
tiplenmis ve `run_id` hic modellenmemisti. M1.2'nin semasi artik
`config_snapshot_ref`'in `account_config_profiles.config_version`'a
(Integer) esdeger oldugunu ve `reports.run_id`'nin (TDD Section 16, v1.1:
run_logs (1)->(1) reports) NOT NULL + UNIQUE bir alan oldugunu netlestirdi.
Repository katmani tasarlanirken bu iki alanin (biri eksik, digeri yanlis
tipte) domain modelini eksik biraktigi ortaya cikti; DDD geregi domain
modeli tam kalmalidir - `run_id` eklenir, `config_snapshot_ref` `int`'e
duzeltilir.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field


class Report(BaseModel):
    """PRD Section 15.5 - Report."""

    report_id: UUID
    account_id: UUID
    run_id: UUID
    generated_at: datetime

    included_job_ids: list[str] = Field(default_factory=list)
    top_matches: list[str] = Field(default_factory=list)

    format: str = "Markdown"
    config_snapshot_ref: int = Field(ge=1)
    storage_path: Path
