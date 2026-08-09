"""filtering/location_filter.py icin birim testleri (Roadmap M6.2, FR-3,
PRD Section 11.1, EDGE-3).

Roadmap M6.2 "Tamamlanma Dogrulamasi": "Istanbul on-site/hybrid, Istanbul
disi, ve belirsiz ('Remote - Turkey') durumlarini kapsayan birim
testleri."

Proje talimatiyla acikca onaylanan mimari karar: `location_filter.py`
SAF bir fonksiyondur (M6.1'in `blacklist_filter.py` ile ayni desen) ve
hedef lokasyon listesini (`target_locations: list[str]`) dogrudan
parametre olarak alir - CLAUDE.md'nin acikca belirttigi "target
location(s)... must live in human-readable config, never hardcoded"
kuralina uyarak "Istanbul" hicbir yerde sabit-kodlanmaz.

Belirsizlik (EDGE-3) cozumu: On-site/Hybrid bir ilan HER ZAMAN gercek bir
ofis lokasyonu belirtir (o yuzden hedefte degilse KESIN reddedilir);
yalnizca Remote (veya workplace_type hic belirtilmemis) bir ilan, konumun
Istanbul'a bagli olup olmadigini ORTAYA KOYMAYABILIR - PRD 11.1'in
"Uzaktan/hibrit ilanlar sirket/pozisyon Istanbul merkezliyse tercih
edilir" cumlesi ve EDGE-3'un tam da bu ornegi ("Uzaktan ilan, hicbir
sehir/ulke bilgisi icermiyor") vermesiyle tutarlidir. Bu ayrim, herhangi
bir sehir-listesi veya virgul-ayristirma sezgisi ICAT ETMEDEN, sadece
JobPosting'in zaten var olan `workplace_type` alanindan turer.
"""

from __future__ import annotations

from datetime import UTC, datetime

from linkedinbot.domain.job_posting import JobPosting, WorkplaceType
from linkedinbot.filtering.location_filter import filter_by_location

COLLECTED_AT = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
TARGET_LOCATIONS = ["Istanbul"]


def _job_posting(**overrides) -> JobPosting:
    data = {
        "job_id": "https://www.linkedin.com/jobs/view/1",
        "title": "Sales Executive",
        "company_id": "Acme Corp",
        "location": "Istanbul, Turkey",
        "posted_date": COLLECTED_AT,
        "description": "Managing key accounts.",
        "application_url": "https://www.linkedin.com/jobs/view/1",
        "collected_at": COLLECTED_AT,
    }
    data.update(overrides)
    return JobPosting(**data)


def test_istanbul_on_site_job_passes():
    job_posting = _job_posting(
        location="Istanbul, Turkey", workplace_type=WorkplaceType.ON_SITE
    )

    result = filter_by_location(job_posting, TARGET_LOCATIONS)

    assert result.passed is True


def test_istanbul_hybrid_job_passes():
    job_posting = _job_posting(location="Istanbul, Turkey", workplace_type=WorkplaceType.HYBRID)

    result = filter_by_location(job_posting, TARGET_LOCATIONS)

    assert result.passed is True


def test_matching_is_case_insensitive_and_tolerates_extra_text():
    job_posting = _job_posting(location="istanbul, turkiye", workplace_type=WorkplaceType.ON_SITE)

    result = filter_by_location(job_posting, TARGET_LOCATIONS)

    assert result.passed is True


def test_on_site_job_outside_istanbul_is_rejected_definitively():
    job_posting = _job_posting(location="Ankara, Turkey", workplace_type=WorkplaceType.ON_SITE)

    result = filter_by_location(job_posting, TARGET_LOCATIONS)

    assert result.passed is False
    assert "Ankara, Turkey" in result.reason
    assert "Unclear" not in result.reason


def test_hybrid_job_outside_istanbul_is_rejected_definitively():
    job_posting = _job_posting(location="Ankara, Turkey", workplace_type=WorkplaceType.HYBRID)

    result = filter_by_location(job_posting, TARGET_LOCATIONS)

    assert result.passed is False
    assert "Unclear" not in result.reason


def test_ambiguous_remote_turkey_job_is_rejected_and_marked_location_unclear():
    # PRD Section 11.1's own canonical example + EDGE-3.
    job_posting = _job_posting(location="Remote - Turkey", workplace_type=WorkplaceType.REMOTE)

    result = filter_by_location(job_posting, TARGET_LOCATIONS)

    assert result.passed is False
    assert "Location Unclear" in result.reason


def test_remote_job_naming_istanbul_is_preferred_and_passes():
    # PRD 11.1: "Uzaktan (Remote) veya hibrit ilanlar, sirketin/pozisyonun
    # Istanbul merkezli olmasi durumunda tercih edilir."
    job_posting = _job_posting(
        location="Remote - Istanbul, Turkey", workplace_type=WorkplaceType.REMOTE
    )

    result = filter_by_location(job_posting, TARGET_LOCATIONS)

    assert result.passed is True


def test_job_with_unspecified_workplace_type_and_no_istanbul_mention_is_ambiguous():
    job_posting = _job_posting(location="Turkey", workplace_type=None)

    result = filter_by_location(job_posting, TARGET_LOCATIONS)

    assert result.passed is False
    assert "Location Unclear" in result.reason


def test_turkish_capitalized_istanbul_still_matches_the_target_location():
    # Gercek bir hata: Python'in `str.lower()`'i, Turkce noktali buyuk
    # harf "I"yi ("Istanbul"), ASCII "i" yerine "i" + BIRLESIK NOKTA
    # (U+0307) ikilisine cevirir - bu yuzden naif bir `.lower()` karsilastirmasi,
    # doğru yazılmış Turkce "İstanbul, Türkiye" dizesini "istanbul" hedefiyle
    # ESLESTIREMEZ (yanlis negatif) - bkz. self-review bulgusu.
    job_posting = _job_posting(location="İstanbul, Türkiye", workplace_type=WorkplaceType.ON_SITE)

    result = filter_by_location(job_posting, TARGET_LOCATIONS)

    assert result.passed is True


def test_location_filter_never_sets_a_confidence_value():
    passing = filter_by_location(
        _job_posting(location="Istanbul, Turkey", workplace_type=WorkplaceType.ON_SITE),
        TARGET_LOCATIONS,
    )
    rejecting = filter_by_location(
        _job_posting(location="Ankara, Turkey", workplace_type=WorkplaceType.ON_SITE),
        TARGET_LOCATIONS,
    )

    assert passing.confidence is None
    assert rejecting.confidence is None
