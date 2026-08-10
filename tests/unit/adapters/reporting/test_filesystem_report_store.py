"""FilesystemReportStore icin birim testleri (Roadmap M8.3, FR-17, TDD
Section 18 adim 3).

TDD Section 18 adim 3'un TAM METNI: "**`ReportStore` Port** cagirilir;
V1 uygulamasi (`FilesystemReportStore`) dosyayi
`reports/{account_id}/{YYYY-MM-DD}_{report_id}.md` yoluna yazar (FR-17 -
uzerine yazma yok, her calistirma kendi dosyasini uretir)."

Bu modul SAF bir dosya-IO adaptoru test eder - DB'ye hicbir sekilde
dokunmaz (bkz. `tests/integration/db/test_report_persistence.py` for the
Roadmap'in kendi "iki ardisik derleme -> iki dosya + iki DB satiri"
Tamamlanma Dogrulamasi'ni kapsayan entegrasyon testi). `base_dir`
(`reports/` kokunun nerede yasadigi), `adapters/secrets/
local_keyring_adapter.py`'nin (M2.3, degistirilmemis) `secrets_file_path`
deseniyle AYNI sekilde constructor'dan enjekte edilir - adaptor KENDISI
konumu nereden bulacagina KARAR VERMEZ (bu, NFR-6/Config-Is Mantigi
Ayrimi ile tutarlidir ve testedilebilirlik saglar - gercek bir "reports/"
dizinine dokunmadan `tmp_path` ile tam izolasyon).

FR-17'nin "uzerine yazma yok" gereksinimi, Port'un kendi sozlesmesinin bir
PARCASI olarak (yalnizca bu V1 adaptorunun rastgele bir secimi degil)
KASITLI OLARAK aktif bir kontrolle uygulanir: hedef dosya zaten varsa
adaptor `FileExistsError` firlatir - `report_id` her cagirida taze bir
UUID oldugu icin pratikte NEREDEYSE hic tetiklenmez, ama bu, FR-17'yi bir
VARSAYIM olarak degil, DENETLENEBILIR bir DEGISMEZ (invariant) olarak
kodlar (ayni projenin "asla sessizce varsayilan davranisa donme" ilkesiyle
tutarli, bkz. EDGE-15/FR-13).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from linkedinbot.adapters.reporting.filesystem_report_store import FilesystemReportStore
from linkedinbot.ports.report_store_port import ReportStorePort

GENERATED_AT = datetime(2026, 8, 10, 9, 30, tzinfo=UTC)


def test_filesystem_report_store_implements_the_port(tmp_path: Path):
    store = FilesystemReportStore(base_dir=tmp_path)
    assert isinstance(store, ReportStorePort)


def test_save_writes_the_content_at_the_prescribed_path(tmp_path: Path):
    # TDD Section 18 adim 3: reports/{account_id}/{YYYY-MM-DD}_{report_id}.md
    account_id = uuid4()
    report_id = uuid4()
    store = FilesystemReportStore(base_dir=tmp_path)

    path = store.save(account_id, report_id, GENERATED_AT, "# Job Report\n\ncontent")

    expected_path = tmp_path / str(account_id) / f"2026-08-10_{report_id}.md"
    assert path == expected_path
    assert path.read_text(encoding="utf-8") == "# Job Report\n\ncontent"


def test_save_creates_the_account_directory_when_missing(tmp_path: Path):
    account_id = uuid4()
    report_id = uuid4()
    store = FilesystemReportStore(base_dir=tmp_path)

    assert not (tmp_path / str(account_id)).exists()

    store.save(account_id, report_id, GENERATED_AT, "content")

    assert (tmp_path / str(account_id)).is_dir()


def test_save_never_overwrites_an_existing_report(tmp_path: Path):
    # FR-17: "uzerine yazilmadan kalici hale gelir" - ayni (account_id,
    # report_id, generated_at) ucluesuyle ikinci bir save() cagirisi
    # basarisiz OLMALIDIR, sessizce ilk dosyanin uzerine yazmamalidir.
    account_id = uuid4()
    report_id = uuid4()
    store = FilesystemReportStore(base_dir=tmp_path)
    store.save(account_id, report_id, GENERATED_AT, "original content")

    with pytest.raises(FileExistsError):
        store.save(account_id, report_id, GENERATED_AT, "different content")

    expected_path = tmp_path / str(account_id) / f"2026-08-10_{report_id}.md"
    assert expected_path.read_text(encoding="utf-8") == "original content"


def test_two_different_report_ids_produce_two_different_files(tmp_path: Path):
    account_id = uuid4()
    store = FilesystemReportStore(base_dir=tmp_path)

    path_1 = store.save(account_id, uuid4(), GENERATED_AT, "first")
    path_2 = store.save(account_id, uuid4(), GENERATED_AT, "second")

    assert path_1 != path_2
    assert path_1.read_text(encoding="utf-8") == "first"
    assert path_2.read_text(encoding="utf-8") == "second"


def test_different_accounts_are_isolated_in_separate_subdirectories(tmp_path: Path):
    account_a = uuid4()
    account_b = uuid4()
    report_id = uuid4()
    store = FilesystemReportStore(base_dir=tmp_path)

    path_a = store.save(account_a, report_id, GENERATED_AT, "for a")
    path_b = store.save(account_b, report_id, GENERATED_AT, "for b")

    assert path_a.parent == tmp_path / str(account_a)
    assert path_b.parent == tmp_path / str(account_b)
    assert path_a != path_b
