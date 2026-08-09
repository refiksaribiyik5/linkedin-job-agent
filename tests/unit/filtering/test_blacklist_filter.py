"""filtering/blacklist_filter.py icin birim testleri (Roadmap M6.1, FR-19).

Roadmap M6.1 "Tamamlanma Dogrulamasi": "Blacklist'e alinmis bir sirket
fixture'i ile birim testi." FR-19 kabul kriteri: dislanan bir sirket/ilan
tum filtrelerden gecse ve yuksek skor alsa dahi hicbir raporda gorunmez.

Proje talimatiyla acikca onaylanan mimari karar: `blacklist_filter.py`
SAF bir fonksiyondur - `diff_engine.py`/`normalizer.py` (M4.1/M4.2) ile
AYNI desen: herhangi bir repository/DB'ye ERISMEZ, LLM Gateway'e HIC
ihtiyac duymaz (TDD Section 11.4: Blacklist "saf bir konfigurasyon-lookup
islemidir"). `UserProfile.preferences` (M1.1, domain/user_profile.py)
zaten FR-19'un TEK somut icerigini (`excluded_companies`,
`excluded_job_ids`) tasir - bu yuzden fonksiyon dogrudan `Preferences`'i
parametre olarak alir (AccountContext'in tamamini degil - M2.2
"Bagimliliklar" notu, blacklist verisinin runtime'da nereden geldigini
belirtir, fonksiyonun imzasini degil; `diff_engine.py`'nin kendi minimal
parametre yaklasimiyla tutarlidir).
"""

from __future__ import annotations

from datetime import UTC, datetime

from linkedinbot.domain.job_posting import JobPosting
from linkedinbot.domain.user_profile import Preferences
from linkedinbot.filtering.blacklist_filter import filter_by_blacklist

COLLECTED_AT = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


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


def test_job_from_excluded_company_is_rejected_with_a_reason_naming_the_company():
    job_posting = _job_posting(company_id="Acme Corp")
    preferences = Preferences(excluded_companies=["Acme Corp"], excluded_job_ids=[])

    result = filter_by_blacklist(job_posting, preferences)

    assert result.passed is False
    assert "Acme Corp" in result.reason


def test_job_with_excluded_job_id_is_rejected_with_a_reason_naming_the_job():
    job_id = "https://www.linkedin.com/jobs/view/999"
    job_posting = _job_posting(
        job_id=job_id, application_url=job_id, company_id="Some Other Company"
    )
    preferences = Preferences(excluded_companies=[], excluded_job_ids=[job_id])

    result = filter_by_blacklist(job_posting, preferences)

    assert result.passed is False
    assert job_id in result.reason


def test_job_not_on_either_list_passes():
    job_posting = _job_posting(company_id="Unrelated Company")
    preferences = Preferences(
        excluded_companies=["Acme Corp"], excluded_job_ids=["https://example.com/other"]
    )

    result = filter_by_blacklist(job_posting, preferences)

    assert result.passed is True


def test_job_passes_when_preferences_have_no_exclusions_at_all():
    job_posting = _job_posting()
    preferences = Preferences()

    result = filter_by_blacklist(job_posting, preferences)

    assert result.passed is True


def test_blacklist_filter_never_sets_a_confidence_value():
    # Blacklist ikili/deterministik bir konfigurasyon-lookup'tir (TDD
    # Section 11.4) - Department filtresinin aksine bir guven skoru
    # tasimaz.
    passing = filter_by_blacklist(_job_posting(), Preferences())
    rejecting = filter_by_blacklist(
        _job_posting(company_id="Acme Corp"),
        Preferences(excluded_companies=["Acme Corp"]),
    )

    assert passing.confidence is None
    assert rejecting.confidence is None
