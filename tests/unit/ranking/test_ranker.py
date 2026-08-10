"""ranking/ranker.py icin birim testleri (Roadmap M8.1, FR-11, PRD Section
16.1/16.4).

Roadmap M8.1 "Amac": "FR-11'i uygulamak - departman bazli gruplama + Top
N; Closed/Excluded durumundaki ilanlari dislamak." "Beklenen Sonuc":
"Karma durumlu bir ilan setinden Closed/Excluded olanlar hem grup hem
Top-N ciktisinda gorunmez; Top-N, AI Match Score'a gore azalan siradadir."

Proje talimatiyla acikca onaylanan mimari kararlar:
- Bu modul SAF fonksiyonlardan olusur (`diff_engine.py`/M4.2 ile ayni
  desen): hicbir depoya/DB'ye erismez, dogrudan `EvaluatedJob` (M1.1,
  degistirilmemis) listesi alir.
- `group_by_department`, PRD Section 16.1'in "Departman bazli bolumler
  (sadece NEW ve UPDATED ilanlar)" kuralini uygular - SEEN, Closed,
  Excluded durumundaki ilanlar HICBIR gruba dahil edilmez.
- `rank_top_matches`, Section 16.1'in "acik kalan en iyi firsatlarin
  aninstik goruntusu... daha once raporlanmis ama hala guclu ve acik
  olan ilanlar burada tekrar gorunebilir" kuralini uygular - NEW/SEEN/
  UPDATED HEPSI uygun adaydir (yalnizca Closed/Excluded haric tutulur);
  `ai_match_score` None olan (Scoring Unavailable) ilanlar, "skora gore
  azalan sirada" siralanamayacaklarindan doganl olarak Top-N adaylarindan
  cikarilir - bu, YENI bir is kurali degil, "skora gore sirala"
  isleminin dogal bir sonucudur.
- `department_cluster` alani None olan bir ilan HICBIR gruba dahil
  edilemez (gruplanacak bir anahtari yoktur) - Top-N'i etkilemez.
- `top_n`, M6.2/M6.4'un `target_locations`/`confidence_threshold`
  deseniyle AYNI sekilde dogrudan cagirana birakilan duz bir
  parametredir - hicbir yerde sabit-kodlanmaz (varsayilan 10, PRD
  Section 17, ama bu VARSAYILAN deger burada YOKTUR).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from linkedinbot.domain.evaluated_job import EvaluatedJob, JobStatus, MatchRationaleItem
from linkedinbot.ranking.ranker import group_by_department, rank_top_matches

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
ACCOUNT_ID = uuid4()

_RATIONALE = [
    MatchRationaleItem(component="Department/Role Relevance", value="0.9", explanation="Fits."),
    MatchRationaleItem(component="Experience Level Fit", value="Yes", explanation="Matches."),
    MatchRationaleItem(component="Location Fit", value="Yes", explanation="Matches."),
]


def _job(**overrides) -> EvaluatedJob:
    data = {
        "account_id": ACCOUNT_ID,
        "job_id": "https://www.linkedin.com/jobs/view/1",
        "company_id": "Acme Corp",
        "ai_match_score": 80.0,
        "match_rationale": _RATIONALE,
        "department_cluster": "Sales & Business Development",
        "status": JobStatus.NEW,
        "first_seen_at": NOW,
        "last_seen_at": NOW,
        "content_hash_at_evaluation": "hash-1",
        "config_version_used": 1,
    }
    data.update(overrides)
    return EvaluatedJob(**data)


# ---------------------------------------------------------------------------
# group_by_department
# ---------------------------------------------------------------------------


def test_new_and_updated_jobs_are_grouped_by_their_department_cluster():
    new_job = _job(job_id="job-1", status=JobStatus.NEW, department_cluster="Sales")
    updated_job = _job(job_id="job-2", status=JobStatus.UPDATED, department_cluster="Marketing")

    groups = group_by_department([new_job, updated_job])

    assert groups == {"Sales": [new_job], "Marketing": [updated_job]}


def test_multiple_jobs_in_the_same_cluster_are_grouped_together():
    job_a = _job(job_id="job-1", department_cluster="Sales")
    job_b = _job(job_id="job-2", department_cluster="Sales")

    groups = group_by_department([job_a, job_b])

    assert groups == {"Sales": [job_a, job_b]}


def test_seen_jobs_are_excluded_from_department_groups():
    # PRD 16.1: "daha once degismeden raporlanmis ilanlar bu bolumlerde
    # tekrar gosterilmez" - SEEN, department gruplarindan haric tutulur.
    seen_job = _job(status=JobStatus.SEEN)

    groups = group_by_department([seen_job])

    assert groups == {}


def test_closed_and_excluded_jobs_are_excluded_from_department_groups():
    closed_job = _job(job_id="job-1", status=JobStatus.CLOSED)
    excluded_job = _job(job_id="job-2", status=JobStatus.EXCLUDED)

    groups = group_by_department([closed_job, excluded_job])

    assert groups == {}


def test_job_without_a_department_cluster_is_excluded_from_all_groups():
    job = _job(department_cluster=None)

    groups = group_by_department([job])

    assert groups == {}


def test_group_by_department_on_empty_input_returns_empty_dict():
    assert group_by_department([]) == {}


# ---------------------------------------------------------------------------
# rank_top_matches
# ---------------------------------------------------------------------------


def test_top_matches_are_sorted_by_ai_match_score_descending():
    low = _job(job_id="job-low", ai_match_score=50.0)
    high = _job(job_id="job-high", ai_match_score=95.0)
    mid = _job(job_id="job-mid", ai_match_score=70.0)

    result = rank_top_matches([low, high, mid], top_n=10)

    assert result == [high, mid, low]


def test_top_matches_respects_the_top_n_limit():
    jobs = [_job(job_id=f"job-{i}", ai_match_score=float(i)) for i in range(5)]

    result = rank_top_matches(jobs, top_n=2)

    assert [job.job_id for job in result] == ["job-4", "job-3"]


def test_top_matches_with_top_n_zero_returns_an_empty_list():
    # Self-review: `candidates[:top_n]` icin sinir davranisi acikca
    # dogrulanir - top_n=0, "hic ilan isteme" seklinde yorumlanir
    # (Python slice semantigi zaten dogru davranir, ama bu davranis
    # burada acikca test edilmemisti).
    jobs = [_job(job_id=f"job-{i}", ai_match_score=float(i)) for i in range(3)]

    assert rank_top_matches(jobs, top_n=0) == []


def test_top_matches_includes_seen_jobs_that_are_still_open_and_strong():
    # PRD 16.1: "daha once raporlanmis ama hala guclu ve acik olan
    # ilanlar burada tekrar gorunebilir" - SEEN, Top Matches'ten haric
    # tutulmaz (Departman gruplarindan farkli olarak).
    seen_job = _job(status=JobStatus.SEEN, ai_match_score=90.0)

    result = rank_top_matches([seen_job], top_n=10)

    assert result == [seen_job]


def test_top_matches_excludes_closed_and_excluded_jobs():
    closed_job = _job(job_id="job-1", status=JobStatus.CLOSED, ai_match_score=99.0)
    excluded_job = _job(job_id="job-2", status=JobStatus.EXCLUDED, ai_match_score=98.0)
    open_job = _job(job_id="job-3", status=JobStatus.NEW, ai_match_score=50.0)

    result = rank_top_matches([closed_job, excluded_job, open_job], top_n=10)

    assert result == [open_job]


def test_top_matches_excludes_jobs_with_an_unavailable_ai_match_score():
    scored_job = _job(job_id="job-1", ai_match_score=70.0)
    unavailable_job = _job(job_id="job-2", ai_match_score=None, match_rationale=None)

    result = rank_top_matches([scored_job, unavailable_job], top_n=10)

    assert result == [scored_job]


def test_rank_top_matches_on_empty_input_returns_empty_list():
    assert rank_top_matches([], top_n=10) == []


def test_mixed_status_fixture_matches_roadmaps_own_completion_criterion():
    # Roadmap M8.1'in kendi Tamamlanma Dogrulamasi: "Karma fixture ile
    # birim testi" - Closed/Excluded HEM grup HEM Top-N ciktisinda
    # gorunmez; Top-N azalan AI Match Score sirasindadir.
    new_sales = _job(
        job_id="new-sales", status=JobStatus.NEW, department_cluster="Sales", ai_match_score=92.0
    )
    updated_marketing = _job(
        job_id="updated-marketing",
        status=JobStatus.UPDATED,
        department_cluster="Marketing",
        ai_match_score=75.0,
    )
    seen_strong = _job(
        job_id="seen-strong",
        status=JobStatus.SEEN,
        department_cluster="Sales",
        ai_match_score=88.0,
    )
    closed = _job(
        job_id="closed", status=JobStatus.CLOSED, department_cluster="Sales", ai_match_score=99.0
    )
    excluded = _job(
        job_id="excluded",
        status=JobStatus.EXCLUDED,
        department_cluster="Marketing",
        ai_match_score=97.0,
    )
    mixed = [new_sales, updated_marketing, seen_strong, closed, excluded]

    groups = group_by_department(mixed)
    top_matches = rank_top_matches(mixed, top_n=10)

    # Gruplar: yalnizca NEW/UPDATED (seen_strong SEEN oldugu icin
    # gruplarda YOK, closed/excluded ise durumlari geregi hic yok).
    assert groups == {"Sales": [new_sales], "Marketing": [updated_marketing]}
    # Top-N: closed/excluded YOK; kalanlar AI Match Score'a gore azalan.
    assert top_matches == [new_sales, seen_strong, updated_marketing]
