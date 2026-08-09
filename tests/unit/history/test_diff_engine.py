"""history/diff_engine.py icin birim testleri (Roadmap M4.2, FR-8/FR-9/FR-10/FR-14).

Roadmap M4.2 "Tamamlanma Dogrulamasi": "Kontrollu bir fixture setiyle (bir
degismemis, bir degismis, bir kaybolmus, bir yeni ilan) diff engine iki kez
calistirilir; sirasiyla Seen/Updated/Closed/New dogrulanir."

Proje talimatiyla acikca onaylanan mimari karar: `diff_engine.py` SAF bir
fonksiyondur - herhangi bir repository/DB'ye ERISMEZ (M4.1'in
normalizer.py'siyle AYNI desen). "Gecmis kayitlar," cagiran tarafindan
(henuz insa edilmemis bir Orchestrator, M9) acikca bir parametre olarak
verilir; bu modul EvaluatedJobRepositoryPort'u (M1.3) IMPORT ETMEZ.
"""

from __future__ import annotations

from linkedinbot.domain.evaluated_job import JobStatus
from linkedinbot.domain.job_posting import JobPosting
from linkedinbot.history.diff_engine import PreviousEvaluation, diff_job_postings

COLLECTED_AT = "2026-08-09T12:00:00+00:00"


def _job_posting(job_id: str, **overrides) -> JobPosting:
    data = {
        "job_id": job_id,
        "title": "Sales Executive",
        "company_id": "Acme Corp",
        "location": "Istanbul, Turkey",
        "posted_date": COLLECTED_AT,
        "description": "Original description.",
        "application_url": f"https://www.linkedin.com/jobs/view/{job_id}",
        "collected_at": COLLECTED_AT,
    }
    data.update(overrides)
    return JobPosting(**data)


# ---------------------------------------------------------------------------
# Roadmap M4.2'nin kendi Tamamlanma Dogrulamasi - birebir uctan uca senaryo:
# diff engine iki kez calistirilir (bir degismemis, bir degismis, bir
# kaybolmus, bir yeni ilan).
# ---------------------------------------------------------------------------


def test_diff_job_postings_full_roadmap_scenario_across_two_runs():
    unchanged = _job_posting("unchanged-1")
    changing_v1 = _job_posting("changing-1", description="Original description.")
    vanishing = _job_posting("vanishing-1")

    # --- Calistirma 1: gecmis yok, hepsi New olmali ---
    run_1_scan = [
        (unchanged, "hash-unchanged"),
        (changing_v1, "hash-changing-v1"),
        (vanishing, "hash-vanishing"),
    ]
    run_1_results, run_1_closed = diff_job_postings(run_1_scan, previous_evaluations={})

    assert {job_posting.job_id: status for job_posting, status in run_1_results} == {
        "unchanged-1": JobStatus.NEW,
        "changing-1": JobStatus.NEW,
        "vanishing-1": JobStatus.NEW,
    }
    assert run_1_closed == []

    # Calistirma 1'in sonucundan "gecmis kayitlar" insa edilir (Orchestrator'in
    # M9'da yapacagi seyin sadelestirilmis karsiligi).
    previous_evaluations = {
        job_posting.job_id: PreviousEvaluation(status=status, content_hash=content_hash)
        for (job_posting, content_hash), (_jp, status) in zip(
            run_1_scan, run_1_results, strict=True
        )
    }

    # --- Calistirma 2: unchanged AYNI, changing FARKLI icerikli, vanishing
    # taramada YOK, yeni bir ilan VAR ---
    changing_v2 = _job_posting("changing-1", description="Completely different text.")
    new_job = _job_posting("new-1")

    run_2_scan = [
        (unchanged, "hash-unchanged"),  # ayni hash -> Seen
        (changing_v2, "hash-changing-v2"),  # farkli hash -> Updated
        (new_job, "hash-new"),  # gecmiste yok -> New
        # vanishing bu taramada YOK -> Closed
    ]
    run_2_results, run_2_closed = diff_job_postings(run_2_scan, previous_evaluations)

    assert {job_posting.job_id: status for job_posting, status in run_2_results} == {
        "unchanged-1": JobStatus.SEEN,
        "changing-1": JobStatus.UPDATED,
        "new-1": JobStatus.NEW,
    }
    assert run_2_closed == ["vanishing-1"]


# ---------------------------------------------------------------------------
# Bireysel durum gecisleri
# ---------------------------------------------------------------------------


def test_diff_job_postings_marks_never_before_seen_job_as_new():
    job_posting = _job_posting("job-1")

    results, closed = diff_job_postings([(job_posting, "hash-1")], previous_evaluations={})

    assert results == [(job_posting, JobStatus.NEW)]
    assert closed == []


def test_diff_job_postings_marks_unchanged_job_as_seen():
    job_posting = _job_posting("job-1")
    previous = {"job-1": PreviousEvaluation(status=JobStatus.SEEN, content_hash="hash-1")}

    results, _closed = diff_job_postings([(job_posting, "hash-1")], previous)

    assert results == [(job_posting, JobStatus.SEEN)]


def test_diff_job_postings_marks_changed_job_as_updated():
    job_posting = _job_posting("job-1")
    previous = {"job-1": PreviousEvaluation(status=JobStatus.SEEN, content_hash="hash-old")}

    results, _closed = diff_job_postings([(job_posting, "hash-new")], previous)

    assert results == [(job_posting, JobStatus.UPDATED)]


def test_diff_job_postings_marks_missing_active_job_as_closed():
    previous = {"job-1": PreviousEvaluation(status=JobStatus.SEEN, content_hash="hash-1")}

    results, closed = diff_job_postings([], previous)

    assert results == []
    assert closed == ["job-1"]


def test_diff_job_postings_reopens_a_previously_closed_job_as_new():
    # TDD Section 17 durum makinesi: "Closed -> New (yeniden acilma, EDGE-5)."
    job_posting = _job_posting("job-1")
    previous = {"job-1": PreviousEvaluation(status=JobStatus.CLOSED, content_hash="hash-1")}

    # Icerik AYNI kalmis olsa bile (hash-1), Closed'dan donen bir ilan
    # Seen/Updated degil, NEW olarak yeniden baslar.
    results, closed = diff_job_postings([(job_posting, "hash-1")], previous)

    assert results == [(job_posting, JobStatus.NEW)]
    assert closed == []


def test_diff_job_postings_does_not_re_report_an_already_closed_job_as_closed_again():
    # Bir ilan ONCEKI bir taramada ZATEN Closed olarak isaretlenmisse ve
    # hala taramada gorunmuyorsa, "closed" listesine TEKRAR eklenmemelidir
    # - bu, zaten bilinen bir durumun gereksiz yere tekrar bildirilmesidir.
    previous = {"job-1": PreviousEvaluation(status=JobStatus.CLOSED, content_hash="hash-1")}

    results, closed = diff_job_postings([], previous)

    assert results == []
    assert closed == []


# ---------------------------------------------------------------------------
# Kenar durumlar
# ---------------------------------------------------------------------------


def test_diff_job_postings_deduplicates_same_job_id_within_a_single_scan():
    # TDD Appendix ("history.diff_engine ... Duplicate ... tespiti", FR-8) +
    # M3.3'un kendi ic-denetiminde tespit edilen, kabul edilmis bir risk:
    # ayni gercek ilan, ortusen departman aramalari yuzunden AYNI taramada
    # birden fazla kez toplanabilir. Diff Engine, bu tekrarlari TEK bir
    # sonuca indirgemelidir - aksi halde ayni ilan nihai raporda iki kez
    # gorunurdu.
    job_posting_first = _job_posting("job-1", description="First occurrence.")
    job_posting_duplicate = _job_posting("job-1", description="First occurrence.")

    results, _closed = diff_job_postings(
        [(job_posting_first, "hash-1"), (job_posting_duplicate, "hash-1")],
        previous_evaluations={},
    )

    assert len(results) == 1
    assert results[0] == (job_posting_first, JobStatus.NEW)


def test_diff_job_postings_empty_scan_and_empty_history_produces_nothing():
    results, closed = diff_job_postings([], previous_evaluations={})

    assert results == []
    assert closed == []


def test_diff_job_postings_is_deterministic_for_the_same_input():
    job_posting = _job_posting("job-1")
    previous = {"job-1": PreviousEvaluation(status=JobStatus.SEEN, content_hash="hash-1")}

    first_call = diff_job_postings([(job_posting, "hash-1")], previous)
    second_call = diff_job_postings([(job_posting, "hash-1")], previous)

    assert first_call == second_call
