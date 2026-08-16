"""Normalization Service (Roadmap M4.1, FR-14).

TDD Section 6 modul sorumluluklari tablosu: `normalization` modulu "Ham
veriyi JobPosting domain modeline dönüştürür; content_hash'i yalnızca
FR-14'ün 'anlamlı değişiklik' kapsamındaki alanlardan (Title, Experience
Level çıkarımı, Location, Workplace Type, Description) hesaplar" ve
bagimliligi YOKTUR ("saf" bir modul - Playwright/DB/LLM'e dokunmaz). Bu
modul, `collection.collector`'in urettigi `RawJobRecord`'lari (M3.4)
`domain.job_posting.JobPosting`'e (M1.1) donusturur.

KAPSAM KARARLARI (proje talimatiyla acikca onaylandi, M4.1 baslamadan once):

1. **content_hash alan seti**: FR-14/TDD, 5 alan sayar (Title, Experience
   Level, Location, Workplace Type, Description) ama "Experience Level"
   ne `JobPosting` (M1.1) modelinde NE DE `JobPostingOrm` (M1.2) DB
   semasinda HICBIR ZAMAN var olmus bir alandir - ikisi de zaten
   onaylanmis, degistirilmemis sekilleridir. Deneyim seviyesi CIKARIMI
   (inference) TDD Section 10'un kendisi tarafindan AYRI bir Filtreleme
   asamasi (Faz 6) sorumlulugu olarak tanimlanir, Normalizasyon'un degil.
   Bu yuzden `compute_content_hash()` yalnizca GERCEKTEN VAR OLAN 4 alani
   (Title, Location, Workplace Type, Description) kullanir; ne
   `domain/job_posting.py` ne de `db/models.py` bu milestone'da
   DEGISTIRILMEMISTIR.

2. **company_id**: PRD Section 15.2'nin kendisi "Company Name / Company
   ID"yi TEK bir tablo satirinda yazar; su an baska bir sirket-cozumleme
   altyapisi (Company Profile scraping, Faz 7) yoktur. Bu yuzden ham
   taranan sirket ADI dogrudan `company_id` olarak kullanilir.

3. **job_id**: `RawJobRecord`, FR-2'nin minimum alan seti (M3.4) LinkedIn'in
   gercek sayisal ilan ID'sini icermez. `JobPosting.job_id: str` hicbir
   format kisitlamasi tasimadigindan, ham `link` (URL) - mevcut veriyle
   elde edilebilecek en dogal, ilana-ozel benzersiz tanimlayici - dogrudan
   `job_id` olarak kullanilir.

4. **posted_date**: M4.1 zamaninda `RawJobRecord.posted_date` HER ZAMAN
   goreli, ayristirilamayan bir GORUNTU dizesiydi (orn. "3 days ago") -
   bu yuzden `collected_at` ile AYNI deger olarak KASITLI bir yer
   tutucu kullanma karari O ZAMAN dogruydu (bkz. Roadmap'in M4.1'e
   eklenmis ustunluk notu). M10.2'nin `playwright_client.py` yeniden
   yazimi bu onkosulu GECERSIZ kildi: `RawJobRecord.posted_date` artik
   (mevcut oldugunda) LinkedIn'in kendi API'sinden gelen kesin bir
   `YYYY-MM-DD` dizesi tasir. M11.2 (Roadmap Faz 11) bunu kullanir:
   `_parse_listed_date()` bu bicimi ayristirmayi dener; basarili olursa
   GERCEK tarih kullanilir, BASARISIZ olursa (orn. hala eski goreli
   bicimli bir deger, veya beklenmedik baska bir string) `collected_at`
   yedek davranisi DEGISMEDEN korunur - tahmin YURUTULMEZ. Bu, content_hash'i
   HALA ETKILEMEZ - FR-14 posted_date'i zaten "oynak alan" olarak haric
   tutar, bu M11.2 ile DEGISMEDI.

5. **application_url**: `RawJobRecord.link` goreli bir URL ise (orn.
   "/jobs/view/12345"), `JobPosting.application_url` (Pydantic `HttpUrl`)
   olusturulmadan ONCE LinkedIn'in kendi alan adi eklenir - bu bir tahmin
   degil, iyi tanimlanmis, mekanik bir URL normalizasyon kuralidir.

6. **workplace_type / employment_type / easy_apply**: `RawJobRecord`
   (FR-2'nin minimum alan seti) bu veriyi hic tasimaz; `JobPosting`'de
   zaten Optional olduklari icin `None` birakilir.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from urllib.parse import urljoin

from linkedinbot.collection.collector import RawJobRecord
from linkedinbot.domain.job_posting import JobPosting

_LINKEDIN_BASE_URL = "https://www.linkedin.com"
_HASH_FIELD_SEPARATOR = "\x1f"  # ASCII "unit separator" - alan sinirlarinin
# birlestirmede yanlislikla belirsizlesmesini (orn. "A"+"BC" ile "AB"+"C"
# ayni dizeyi uretmesini) onler.
# M11.2: `adapters/linkedin/playwright_client.py::_format_listed_date()`'in
# UREttigi TAM bicim - bu modul (kasitli olarak `adapters.*`e bagimliligi
# OLMADIGI icin) o fonksiyonu DOGRUDAN import ETMEZ, yalnizca ayni bicim
# SOZLESMESINI (informal, testlerle korunan) paylasir.
_LISTED_DATE_FORMAT = "%Y-%m-%d"


def compute_content_hash(job_posting: JobPosting) -> str:
    """FR-14: content_hash yalnizca Title/Location/Workplace Type/Description
    alanlarindan hesaplanir (bkz. modul dokumaninin 1. maddesi - Experience
    Level, mevcut semada hic var olmadigi icin dahil edilmez). Posted Date
    gibi oynak/gurultulu alanlar KASITLI OLARAK dahil edilmez.
    """
    workplace_type_value = job_posting.workplace_type.value if job_posting.workplace_type else ""
    fields = [
        job_posting.title,
        job_posting.location,
        workplace_type_value,
        job_posting.description,
    ]
    normalized = _HASH_FIELD_SEPARATOR.join(fields)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _parse_listed_date(posted_date: str) -> datetime | None:
    """M11.2: `raw_record.posted_date`'i `_LISTED_DATE_FORMAT` bicimine
    karsi ayristirmayi dener. Basarili olursa UTC gece yarisinda bir
    `datetime` doner; herhangi bir bicim uyumsuzlugunda (orn. hala eski
    goreli metin, "3 days ago" gibi, veya beklenmedik baska bir deger)
    `None` doner - tahmin YURUTULMEZ, cagiran `collected_at` yedegine
    duser (bkz. modul dokumaninin 4. maddesi).
    """
    try:
        return datetime.strptime(posted_date, _LISTED_DATE_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def normalize_record(raw_record: RawJobRecord, collected_at: datetime) -> tuple[JobPosting, str]:
    """RawJobRecord (M3.4) -> JobPosting (M1.1) + content_hash donusumu
    (Roadmap M4.1). Alan esleme kararlari icin modul dokumanina bakiniz.

    Doner: `(JobPosting, content_hash)` - TDD Section 8 Veri Akisi
    tablosunun Normalizasyon satirinin ciktisini ("JobPosting[] +
    content_hash") birebir yansitir; `content_hash`, `JobPosting`'in
    KENDI bir alani DEGILDIR (o model M1.1'de zaten onaylanmis, bu
    milestone'da degistirilmemistir).
    """
    application_url = raw_record.link
    if not application_url.startswith(("http://", "https://")):
        application_url = urljoin(_LINKEDIN_BASE_URL, application_url)

    posted_date = _parse_listed_date(raw_record.posted_date) or collected_at

    # Bagimsiz incelemede bulunan Kritik bulgu duzeltmesi: job_id, HER ZAMAN
    # normalize edilmis `application_url`'den turetilmelidir, ham
    # `raw_record.link`'ten DEGIL - aksi halde ayni gercek ilan, goreli mi
    # yoksa mutlak mi bir href yakalandigina bagli olarak FARKLI job_id
    # degerleri uretirdi (bkz. testler).
    job_posting = JobPosting(
        job_id=application_url,
        title=raw_record.title,
        company_id=raw_record.company,
        location=raw_record.location,
        posted_date=posted_date,
        description=raw_record.description,
        application_url=application_url,
        collected_at=collected_at,
    )
    return job_posting, compute_content_hash(job_posting)
