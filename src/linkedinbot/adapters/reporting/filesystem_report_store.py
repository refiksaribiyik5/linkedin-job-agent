"""FilesystemReportStore - ReportStorePort'un V1 uygulamasi (Roadmap M8.3,
FR-17, TDD Section 18 adim 3).

TDD Section 18 adim 3'un TAM METNI: "**`ReportStore` Port** cagirilir;
V1 uygulamasi (`FilesystemReportStore`) dosyayi
`reports/{account_id}/{YYYY-MM-DD}_{report_id}.md` yoluna yazar (FR-17 -
uzerine yazma yok, her calistirma kendi dosyasini uretir)."

`base_dir` (bu formuldeki "reports/" kokunun gercekte diskte NEREDE
yasadigi) constructor'dan enjekte edilir - adaptorun KENDISI bu konumu
nereden bulacagina KARAR VERMEZ. Bu, `adapters/secrets/
local_keyring_adapter.py`'nin (M2.3, degistirilmemis)
`LocalKeyringSecretsProvider.__init__(self, secrets_file_path: Path, ...)`
deseniyle BIREBIR AYNI mimari karardir: gercek konum secimi (bir config
dosyasindan mi, ortam degiskeninden mi geldigi) bu adaptorun degil, onu
kablolayan (gelecekteki M9.2 Orchestrator) katmanin sorumlulugudur -
NFR-6/Config-Is Mantigi Ayrimi ile tutarlidir ve `tmp_path` ile gercek bir
"reports/" dizinine dokunmadan tam izolasyonlu test saglar.

Atomik yazma (gecici dosya + `os.replace()`): `adapters/secrets/
local_keyring_adapter.py`'nin `_write_all()` metoduyla AYNI desen ve AYNI
gerekce (NFR-13 "ya butunuyle uygulanir ya da hic uygulanmaz") - duz
`write_text()` kesinti/cokme durumunda yarim/bozuk bir rapor dosyasi
birakabilir.

FR-17 "uzerine yazma yok" - neden AKTIF bir kontrol (yalnizca bir varsayim
degil): hedef dosya zaten varsa `save()` `FileExistsError` firlatir.
`report_id` her cagirida taze bir UUID oldugundan bu kontrol normal
kullanimda pratikte tetiklenmez, ama FR-17'yi Port'un kendi sozlesmesi
geregi DENETLENEBILIR bir degismez (invariant) olarak kodlar - ayni
projenin baska yerlerde (orn. EDGE-15 config dogrulama, M8.2'nin eksik
lookup'larda YUKSEK SESLE basarisiz olmasi) izledigi "asla sessizce
varsayilan/mevcut davranisa donme" ilkesiyle tutarlidir.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import UUID

from linkedinbot.ports.report_store_port import ReportStorePort


class FilesystemReportStore(ReportStorePort):
    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def save(self, account_id: UUID, report_id: UUID, generated_at: datetime, content: str) -> Path:
        target_dir = self._base_dir / str(account_id)
        target_path = target_dir / f"{generated_at:%Y-%m-%d}_{report_id}.md"

        if target_path.exists():
            raise FileExistsError(
                f"Report already exists at {target_path} - reports are never "
                "overwritten (FR-17)."
            )

        target_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_path_str = tempfile.mkstemp(dir=target_dir, prefix=".report-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(content)
            os.replace(tmp_path_str, target_path)
        except BaseException:
            Path(tmp_path_str).unlink(missing_ok=True)
            raise
        return target_path
