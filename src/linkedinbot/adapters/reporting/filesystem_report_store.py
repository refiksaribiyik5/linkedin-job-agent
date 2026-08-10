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

Atomik yazma + atomik "exclusive create" (istisnai duzeltme, bkz.
"Duzeltme notu" asagida): `adapters/secrets/local_keyring_adapter.py`'nin
`_write_all()` metoduyla AYNI "gecici dosya + icerik butunlugu" deseni
korunur (NFR-13 "ya butunuyle uygulanir ya da hic uygulanmaz" - duz
`write_text()` kesinti/cokme durumunda yarim/bozuk bir rapor dosyasi
birakabilir), ANCAK son "yayinlama" adimi `os.replace()` DEGIL,
`os.link()`'tir - asagidaki duzeltme notuna bakiniz.

FR-17 "uzerine yazma yok" - neden AKTIF, ATOMIK bir kontrol (yalnizca bir
varsayim degil): hedef konum zaten doluysa `save()` `FileExistsError`
firlatir. Bu, Port'un kendi sozlesmesi geregi DENETLENEBILIR bir
degismez (invariant) olarak kodlanir - ayni projenin baska yerlerde
(orn. EDGE-15 config dogrulama, M8.2'nin eksik lookup'larda YUKSEK
SESLE basarisiz olmasi) izledigi "asla sessizce varsayilan/mevcut
davranisa donme" ilkesiyle tutarlidir.

**Duzeltme notu (independent review bulgusu):** Ilk uygulama, bu kontrolu
ayri bir `target_path.exists()` on-kontrolu (sonrasinda kosulsuz
uzerine yazan `os.replace()`) ile yapiyordu - bu IKI ayri islem arasinda
bir TOCTOU penceresi birakiyordu: es zamanli iki `save()` cagirisi AYNI
(account_id, report_id, generated_at) uclusuyle, ikisi de on-kontrolu
"dosya yok" olarak gecebilir ve biri digerinin icerigini SESSIZCE
(hicbir hata firlatilmadan) ezebilirdi - bu, `ReportStorePort.save()`'in
kendi sozlesmesinin ("hicbir zaman sessizce mevcut bir raporun uzerine
yazmaz") ve FR-17'nin dogrudan ihlaliydi; bu ihlal thread'lerle SOMUT
olarak yeniden uretildi ve `os.link()`'e gecilerek DUZELTILDI: `os.link()`
hedef zaten varsa TEK, ATOMIK bir sistem cagrisi (`link(2)`) icinde
`FileExistsError` firlatir ve hedefin icerigine HIC DOKUNMAZ - ayri bir
on-kontrole gerek kalmaz, dolayisiyla TOCTOU penceresi TAMAMEN ortadan
kalkar. Gecici dosya, ya basariyla yayinlandiktan (artik hedefle ayni
inode'u paylasan fazladan bir sabit baglanti) ya da `os.link()`
basarisiz oldugundan sonra HER durumda temizlenir.
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

        target_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_path_str = tempfile.mkstemp(dir=target_dir, prefix=".report-", suffix=".tmp")
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(content)
            try:
                os.link(tmp_path, target_path)
            except FileExistsError:
                raise FileExistsError(
                    f"Report already exists at {target_path} - reports are never "
                    "overwritten (FR-17)."
                ) from None
        finally:
            tmp_path.unlink(missing_ok=True)
        return target_path
