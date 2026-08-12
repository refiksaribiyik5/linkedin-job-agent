from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from linkedinbot.domain.run_log import RunLog, RunStatus, TriggerType


def _base_fields(**overrides):
    fields = {
        "run_id": uuid4(),
        "account_id": uuid4(),
        "trigger_type": TriggerType.SCHEDULED,
        "started_at": datetime(2026, 8, 7, tzinfo=UTC),
        "status": RunStatus.SUCCESS,
    }
    fields.update(overrides)
    return fields


def test_valid_successful_run_log_without_error_detail():
    run = RunLog(**_base_fields())
    assert run.error_detail is None
    assert run.collection_capped is False
    assert run.jobs_collected == 0


def test_valid_failed_run_log_with_error_detail():
    run = RunLog(
        **_base_fields(status=RunStatus.FAILED, error_detail="LinkedIn oturumu gecersiz (FR-1)")
    )
    assert run.status is RunStatus.FAILED


def test_failed_run_log_without_error_detail_raises_validation_error():
    # FR-15: basarisiz bir calistirma sessizce yutulmaz.
    with pytest.raises(ValidationError):
        RunLog(**_base_fields(status=RunStatus.FAILED))


def test_failed_run_log_with_blank_error_detail_raises_validation_error():
    with pytest.raises(ValidationError):
        RunLog(**_base_fields(status=RunStatus.FAILED, error_detail=""))


@pytest.mark.parametrize("field", ["jobs_collected", "jobs_filtered", "jobs_new", "jobs_closed"])
def test_negative_job_counts_raise_validation_error(field):
    with pytest.raises(ValidationError):
        RunLog(**_base_fields(**{field: -1}))


def test_collection_capped_can_be_true_per_fr21():
    run = RunLog(**_base_fields(collection_capped=True))
    assert run.collection_capped is True


def test_valid_partial_run_log_with_partial_reason():
    run = RunLog(
        **_base_fields(
            status=RunStatus.PARTIAL,
            partial_reason="Devre kesici tetiklendi: 5 ardisik LinkedIn hatasi.",
        )
    )
    assert run.status is RunStatus.PARTIAL
    assert run.partial_reason == "Devre kesici tetiklendi: 5 ardisik LinkedIn hatasi."


def test_partial_run_log_without_partial_reason_raises_validation_error():
    # M9.4: partial_reason, status Partial iken zorunludur.
    with pytest.raises(ValidationError):
        RunLog(**_base_fields(status=RunStatus.PARTIAL))


def test_partial_run_log_with_blank_partial_reason_raises_validation_error():
    with pytest.raises(ValidationError):
        RunLog(**_base_fields(status=RunStatus.PARTIAL, partial_reason=""))


def test_success_run_log_with_partial_reason_raises_validation_error():
    # M9.4: partial_reason yalnizca Partial icin kullanilir - error_detail'in
    # yalnizca Failed icin kullanilmasiyla AYNI simetri.
    with pytest.raises(ValidationError):
        RunLog(**_base_fields(status=RunStatus.SUCCESS, partial_reason="should not be allowed"))


def test_failed_run_log_with_partial_reason_raises_validation_error():
    with pytest.raises(ValidationError):
        RunLog(
            **_base_fields(
                status=RunStatus.FAILED,
                error_detail="LinkedIn oturumu gecersiz (FR-1)",
                partial_reason="should not be allowed",
            )
        )


def test_valid_partial_run_log_does_not_require_error_detail():
    # error_detail PRD 15.6'nin kendi adlandirmasiyla 'hata bilgisi'dir ve
    # yalnizca Failed icin zorunludur (bkz. _failed_runs_are_never_silent) -
    # Partial bir calistirma bir hata degildir, error_detail'siz gecerlidir.
    run = RunLog(
        **_base_fields(status=RunStatus.PARTIAL, partial_reason="Devre kesici tetiklendi.")
    )
    assert run.error_detail is None
