from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from linkedinbot.domain.evaluated_job import (
    EvaluatedJob,
    FilterResult,
    JobStatus,
    MatchRationaleItem,
)

NOW = datetime(2026, 8, 7, tzinfo=UTC)

THREE_RATIONALE_ITEMS = [
    MatchRationaleItem(component="department", value="Business Development", explanation="Eslesme"),
    MatchRationaleItem(component="location", value="Istanbul", explanation="Eslesme"),
    MatchRationaleItem(component="experience_level", value="Entry Level", explanation="Eslesme"),
]


def _base_fields(**overrides):
    fields = {
        "account_id": uuid4(),
        "job_id": "linkedin-123",
        "company_id": "company-1",
        "status": JobStatus.NEW,
        "first_seen_at": NOW,
        "last_seen_at": NOW,
        "content_hash_at_evaluation": "hash-abc",
        "config_version_used": 1,
    }
    fields.update(overrides)
    return fields


def test_valid_unscored_evaluated_job():
    job = EvaluatedJob(**_base_fields())
    assert job.id is None
    assert job.ai_match_score is None
    assert job.match_rationale is None
    assert job.is_borderline is False
    assert job.report_appearances_count == 0


def test_id_can_be_populated_after_persistence():
    # M1.3: id, DB-only gizli tutulmaz - repository kalicilik sonrasi bu
    # alani doldurup nesneyi geri doner; domain kimligi yine de
    # account_id+job_id ciftidir (bkz. modul dokumani).
    generated_id = uuid4()
    job = EvaluatedJob(**_base_fields(id=generated_id))
    assert job.id == generated_id


def test_missing_content_hash_at_evaluation_raises_validation_error():
    fields = {k: v for k, v in _base_fields().items() if k != "content_hash_at_evaluation"}
    with pytest.raises(ValidationError):
        EvaluatedJob(**fields)


def test_missing_config_version_used_raises_validation_error():
    fields = {k: v for k, v in _base_fields().items() if k != "config_version_used"}
    with pytest.raises(ValidationError):
        EvaluatedJob(**fields)


def test_config_version_used_below_one_raises_validation_error():
    # Config versiyonlari 1'den baslar (bkz. AccountConfigProfileOrm).
    with pytest.raises(ValidationError):
        EvaluatedJob(**_base_fields(config_version_used=0))


def test_valid_scored_evaluated_job_with_three_rationale_items():
    job = EvaluatedJob(
        **_base_fields(
            ai_match_score=92.0,
            match_rationale=THREE_RATIONALE_ITEMS,
            status=JobStatus.SEEN,
        )
    )
    assert job.ai_match_score == 92.0
    assert len(job.match_rationale) == 3


@pytest.mark.parametrize("out_of_range_score", [-1, 100.1, 150])
def test_ai_match_score_out_of_range_raises_validation_error(out_of_range_score):
    # Roadmap M1.1'in kendi ornegi: "skor araligi disi bir AI Match Score".
    with pytest.raises(ValidationError):
        EvaluatedJob(
            **_base_fields(ai_match_score=out_of_range_score, match_rationale=THREE_RATIONALE_ITEMS)
        )


def test_score_without_rationale_raises_validation_error():
    # FR-7: skor gerekcesiz sunulmaz.
    with pytest.raises(ValidationError):
        EvaluatedJob(**_base_fields(ai_match_score=80.0))


def test_rationale_without_score_raises_validation_error():
    with pytest.raises(ValidationError):
        EvaluatedJob(**_base_fields(match_rationale=THREE_RATIONALE_ITEMS))


def test_rationale_with_fewer_than_three_items_raises_validation_error():
    # FR-7 kabul kriteri: gerekce listesi en az 3 madde icerir.
    with pytest.raises(ValidationError):
        EvaluatedJob(
            **_base_fields(ai_match_score=80.0, match_rationale=THREE_RATIONALE_ITEMS[:2])
        )


def test_is_borderline_is_independent_of_status():
    # TDD Section 17: Borderline durum enum'unun bir kolu degil, ayri bir
    # boolean bayraktir; bir ilan ayni anda New VE Borderline olabilir.
    job = EvaluatedJob(**_base_fields(status=JobStatus.NEW, is_borderline=True))
    assert job.status is JobStatus.NEW
    assert job.is_borderline is True


def test_job_status_has_exactly_five_values_without_borderline():
    assert {s.value for s in JobStatus} == {
        "New",
        "Seen",
        "Updated",
        "Closed",
        "Excluded",
    }


def test_filter_result_confidence_out_of_range_raises_validation_error():
    with pytest.raises(ValidationError):
        FilterResult(passed=True, reason="test", confidence=1.5)


def test_filter_result_matched_cluster_defaults_to_none():
    # M1.1 duzeltmesi (M9.3 tasarim incelemesinde bulunan bosluk):
    # matched_cluster, confidence ile AYNI desende opsiyoneldir -
    # yalnizca departman filtresi doldurur, digerleri None birakir.
    result = FilterResult(passed=True, reason="Listede degil")
    assert result.matched_cluster is None


def test_filter_result_matched_cluster_round_trips_when_provided():
    result = FilterResult(
        passed=True,
        reason="Matched cluster: Sales & Business Development.",
        confidence=0.9,
        matched_cluster="Sales & Business Development",
    )
    assert result.matched_cluster == "Sales & Business Development"


def test_valid_filter_result_detail_keyed_by_filter_name():
    job = EvaluatedJob(
        **_base_fields(
            filter_result_detail={
                "blacklist": FilterResult(passed=True, reason="Listede degil"),
                "location": FilterResult(passed=True, reason="Istanbul", confidence=None),
                "department": FilterResult(passed=True, reason="Eslesme", confidence=0.82),
            }
        )
    )
    assert job.filter_result_detail["department"].confidence == 0.82
