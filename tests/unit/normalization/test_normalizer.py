"""normalization/normalizer.py icin birim testleri (Roadmap M4.1, FR-14).

Roadmap M4.1 "Beklenen Sonuc": "Degismemis bir ilanin iki farkli
taramasinda (oynak alanlar farkli olsa da) content_hash ayni kalir."
"Tamamlanma Dogrulamasi": "yalnizca [oynak] bir alani farkli olan iki
fixture ayni hash'i uretir; Description'i farkli bir ucuncu fixture
farkli hash uretir."

Proje talimatiyla acikca onaylanan kapsam kararlari:
1. content_hash YALNIZCA Title/Location/Workplace Type/Description'dan
   hesaplanir - Experience Level (henuz JobPosting/JobPostingOrm'da HIC
   var olmayan bir alan) ve posted_date (FR-14'un kendi acikca haric
   tuttugu "oynak/goreli zaman ifadesi" alani) KASITLI OLARAK DAHIL
   EDILMEZ. domain/job_posting.py ve db/models.py'ye HICBIR SEKILDE
   dokunulmaz.
2. company_id, ham taranan sirket ADI dizesidir (PRD Section 15.2'nin
   kendisi "Company Name / Company ID"yi TEK bir kavram olarak yazar;
   simdilik baska bir sirket-cozumleme altyapisi yoktur).
3. job_id, ham `link` dizesidir (JobPosting.job_id `str` tipinde HICBIR
   format kisitlamasi tasimaz; LinkedIn'in gercek sayisal ID'sini
   RecordExtractor (M3.4) su an cikarmiyor - URL, mevcut veriyle
   elde edilebilecek en dogal, benzersiz-per-ilan tanimlayicidir).
4. posted_date, `collected_at` ile ayni deger olarak KASITLI bir
   YER TUTUCUDUR (proje talimatiyla acikca onaylandi) - goreli tarih
   metni ("3 gun once" vb.) ayristirmasi bu milestone'un kapsami disinda
   birakilir (dogrulanamayan bicimler hakkinda tahmin yurutulmez).
5. `link` goreli bir URL ise (orn. "/jobs/view/12345"), `application_url`
   (Pydantic `HttpUrl`) olusturulmadan once LinkedIn'in kendi alan
   adi eklenir - bu, tahmin degil, iyi tanimlanmis bir URL normalizasyon
   kuralidir.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from linkedinbot.collection.collector import RawJobRecord
from linkedinbot.domain.job_posting import JobPosting
from linkedinbot.normalization.normalizer import compute_content_hash, normalize_record

COLLECTED_AT = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)


def _raw_record(**overrides) -> RawJobRecord:
    data = {
        "title": "Sales Executive",
        "company": "Acme Corp",
        "location": "Istanbul, Turkey",
        "posted_date": "3 days ago",
        "description": "We are looking for a Sales Executive to join our team.",
        "link": "https://www.linkedin.com/jobs/view/12345",
    }
    data.update(overrides)
    return RawJobRecord(**data)


# ---------------------------------------------------------------------------
# normalize_record - RawJobRecord (M3.4) -> JobPosting (M1.1) alan esleme
# ---------------------------------------------------------------------------


def test_normalize_record_maps_title_location_description_directly():
    raw_record = _raw_record()

    job_posting, _content_hash = normalize_record(raw_record, COLLECTED_AT)

    assert job_posting.title == "Sales Executive"
    assert job_posting.location == "Istanbul, Turkey"
    assert job_posting.description == "We are looking for a Sales Executive to join our team."


def test_normalize_record_uses_raw_company_name_as_company_id():
    raw_record = _raw_record(company="Acme Corp")

    job_posting, _content_hash = normalize_record(raw_record, COLLECTED_AT)

    assert job_posting.company_id == "Acme Corp"


def test_normalize_record_uses_link_as_job_id():
    raw_record = _raw_record(link="https://www.linkedin.com/jobs/view/98765")

    job_posting, _content_hash = normalize_record(raw_record, COLLECTED_AT)

    assert job_posting.job_id == "https://www.linkedin.com/jobs/view/98765"


def test_normalize_record_sets_collected_at_from_caller():
    raw_record = _raw_record()

    job_posting, _content_hash = normalize_record(raw_record, COLLECTED_AT)

    assert job_posting.collected_at == COLLECTED_AT


def test_normalize_record_uses_collected_at_as_posted_date_placeholder():
    # Proje talimatiyla acikca onaylanan yer tutucu karari (bkz. modul
    # dokumaninin 4. maddesi) - goreli tarih metni ayristirilmaz.
    raw_record = _raw_record(posted_date="3 days ago")

    job_posting, _content_hash = normalize_record(raw_record, COLLECTED_AT)

    assert job_posting.posted_date == COLLECTED_AT


def test_normalize_record_leaves_optional_fields_unset():
    # RawJobRecord (FR-2'nin minimum alan seti) workplace_type/employment_type/
    # easy_apply icin hicbir veri tasimaz - bunlar JobPosting'de zaten
    # Optional oldugu icin None olarak birakilir.
    raw_record = _raw_record()

    job_posting, _content_hash = normalize_record(raw_record, COLLECTED_AT)

    assert job_posting.workplace_type is None
    assert job_posting.employment_type is None
    assert job_posting.easy_apply is None


def test_normalize_record_keeps_absolute_link_unchanged():
    raw_record = _raw_record(link="https://www.linkedin.com/jobs/view/12345")

    job_posting, _content_hash = normalize_record(raw_record, COLLECTED_AT)

    assert str(job_posting.application_url) == "https://www.linkedin.com/jobs/view/12345"


def test_normalize_record_prepends_linkedin_domain_to_relative_link():
    raw_record = _raw_record(link="/jobs/view/12345")

    job_posting, _content_hash = normalize_record(raw_record, COLLECTED_AT)

    assert str(job_posting.application_url) == "https://www.linkedin.com/jobs/view/12345"


def test_normalize_record_relative_link_does_not_raise_validation_error():
    # Ic-denetimde ONCEDEN tespit edilen risk: `HttpUrl`, goreli bir
    # dizeyi (semasi/host'u olmayan) dogrudan kabul etmez - bu test,
    # relative-to-absolute donusumun bu hatayi gercekten onledigini
    # kanitlar (yalnizca URL'nin GORUNUSTE dogru olmasini degil).
    raw_record = _raw_record(link="/jobs/view/12345")

    try:
        normalize_record(raw_record, COLLECTED_AT)
    except ValidationError:
        pytest.fail("Goreli link, HttpUrl dogrulama hatasina neden oldu")


def test_normalize_record_job_id_matches_normalized_application_url_for_relative_link():
    # Bagimsiz incelemede bulunan Kritik bulgu: job_id, application_url
    # NORMALIZE EDILMEDEN ONCEKI ham `link` degerinden turetiliyordu -
    # goreli bir link icin job_id ("/jobs/view/12345") ile application_url
    # ("https://www.linkedin.com/jobs/view/12345") FARKLI dizeler
    # oluyordu, ayni gercek ilan icin. job_id, HER ZAMAN normalize
    # edilmis application_url'den turetilmelidir.
    raw_record = _raw_record(link="/jobs/view/12345")

    job_posting, _content_hash = normalize_record(raw_record, COLLECTED_AT)

    assert job_posting.job_id == str(job_posting.application_url)
    assert job_posting.job_id == "https://www.linkedin.com/jobs/view/12345"
    # application_url'in kendisi de hala dogru normalize edilmis olmali.
    assert str(job_posting.application_url) == "https://www.linkedin.com/jobs/view/12345"


def test_normalize_record_relative_and_absolute_links_to_same_posting_produce_same_job_id():
    # Ayni gercek LinkedIn ilanina karsi iki AYRI tarama - biri goreli,
    # biri mutlak bir href yakalamis olabilir (DOM/tarayici davranisina
    # bagli olarak). job_id, hangi bicimde yakalandigindan BAGIMSIZ olarak
    # AYNI olmalidir - aksi halde M4.2'nin Diff Engine'i (bu milestone'un
    # kapsami disinda) ayni ilani her taramada "yeni" sanirdi.
    record_with_relative_link = _raw_record(link="/jobs/view/12345")
    record_with_absolute_link = _raw_record(link="https://www.linkedin.com/jobs/view/12345")

    job_posting_relative, _hash_1 = normalize_record(record_with_relative_link, COLLECTED_AT)
    job_posting_absolute, _hash_2 = normalize_record(record_with_absolute_link, COLLECTED_AT)

    assert job_posting_relative.job_id == job_posting_absolute.job_id


# ---------------------------------------------------------------------------
# compute_content_hash - FR-14: yalnizca Title/Location/Workplace
# Type/Description
# ---------------------------------------------------------------------------


def _job_posting(**overrides) -> JobPosting:
    data = {
        "job_id": "https://www.linkedin.com/jobs/view/12345",
        "title": "Sales Executive",
        "company_id": "Acme Corp",
        "location": "Istanbul, Turkey",
        "posted_date": COLLECTED_AT,
        "description": "We are looking for a Sales Executive to join our team.",
        "application_url": "https://www.linkedin.com/jobs/view/12345",
        "collected_at": COLLECTED_AT,
    }
    data.update(overrides)
    return JobPosting(**data)


def test_compute_content_hash_is_deterministic():
    job_posting = _job_posting()

    assert compute_content_hash(job_posting) == compute_content_hash(job_posting)


def test_compute_content_hash_looks_like_a_sha256_hex_digest():
    content_hash = compute_content_hash(_job_posting())

    assert len(content_hash) == 64
    assert all(char in "0123456789abcdef" for char in content_hash)


def test_compute_content_hash_changes_when_title_changes():
    hash_a = compute_content_hash(_job_posting(title="Sales Executive"))
    hash_b = compute_content_hash(_job_posting(title="Marketing Executive"))

    assert hash_a != hash_b


def test_compute_content_hash_changes_when_location_changes():
    hash_a = compute_content_hash(_job_posting(location="Istanbul, Turkey"))
    hash_b = compute_content_hash(_job_posting(location="Ankara, Turkey"))

    assert hash_a != hash_b


def test_compute_content_hash_changes_when_workplace_type_changes():
    hash_a = compute_content_hash(_job_posting(workplace_type=None))
    hash_b = compute_content_hash(_job_posting(workplace_type="Hybrid"))

    assert hash_a != hash_b


def test_compute_content_hash_changes_when_description_changes():
    # Roadmap M4.1 "Tamamlanma Dogrulamasi"nin dogrudan karsiligi:
    # "Description'i farkli bir ucuncu fixture farkli hash uretir."
    hash_a = compute_content_hash(_job_posting(description="Original description."))
    hash_b = compute_content_hash(_job_posting(description="Completely different text."))

    assert hash_a != hash_b


def test_compute_content_hash_does_not_use_a_naive_separator_prone_to_collision():
    # "A" + "BC" ile "AB" + "C" ayni ham birlestirmeyi ("ABC") uretmemelidir.
    hash_a = compute_content_hash(_job_posting(title="A", location="BC"))
    hash_b = compute_content_hash(_job_posting(title="AB", location="C"))

    assert hash_a != hash_b


# ---------------------------------------------------------------------------
# Roadmap M4.1 "Tamamlanma Dogrulamasi" - uctan uca senaryo: normalize_record
# araciligiyla, yalnizca oynak bir alani (posted_date) farkli olan iki RAW
# kayit AYNI content_hash'i uretir.
# ---------------------------------------------------------------------------


def test_normalize_record_content_hash_is_stable_across_differing_posted_date():
    # Roadmap'in kendi ornegi "goruntulenme sayisi" gibi bizim veri
    # modelimizde (FR-2'nin minimum alan seti) hic var olmayan bir alandir;
    # elimizdeki TEK gercek "oynak" alan (TDD/PRD'nin kendi acikca verdigi
    # "goreli zaman ifadeleri" ornegi) posted_date'tir.
    record_scan_1 = _raw_record(posted_date="3 days ago")
    record_scan_2 = _raw_record(posted_date="4 days ago")

    _job_posting_1, hash_1 = normalize_record(record_scan_1, COLLECTED_AT)
    _job_posting_2, hash_2 = normalize_record(
        record_scan_2, datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)
    )

    assert hash_1 == hash_2


def test_normalize_record_content_hash_changes_when_description_changes():
    record_scan_1 = _raw_record(description="Original description.")
    record_scan_2 = _raw_record(description="Completely different text.")

    _job_posting_1, hash_1 = normalize_record(record_scan_1, COLLECTED_AT)
    _job_posting_2, hash_2 = normalize_record(record_scan_2, COLLECTED_AT)

    assert hash_1 != hash_2
