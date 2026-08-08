from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from linkedinbot.domain.account import Account

NOW = datetime(2026, 8, 7, tzinfo=UTC)


def _base_fields(**overrides):
    fields = {
        "display_name": "Refik Saribiyik",
        "created_at": NOW,
        "status": "active",
    }
    fields.update(overrides)
    return fields


def test_valid_account_without_id_before_persistence():
    # M1.3: account_id, repository tarafindan kalicilik SONRASI doldurulur;
    # olusturulmadan once None olmasi gecerlidir (bkz. modul dokumani).
    account = Account(**_base_fields())
    assert account.account_id is None
    assert account.next_run_at is None


def test_account_id_can_be_populated_after_persistence():
    generated_id = uuid4()
    account = Account(**_base_fields(account_id=generated_id))
    assert account.account_id == generated_id


def test_missing_display_name_raises_validation_error():
    fields = {k: v for k, v in _base_fields().items() if k != "display_name"}
    with pytest.raises(ValidationError):
        Account(**fields)


def test_missing_status_raises_validation_error():
    fields = {k: v for k, v in _base_fields().items() if k != "status"}
    with pytest.raises(ValidationError):
        Account(**fields)


def test_next_run_at_defaults_to_none():
    account = Account(**_base_fields())
    assert account.next_run_at is None


def test_next_run_at_can_be_set():
    account = Account(**_base_fields(next_run_at=NOW))
    assert account.next_run_at == NOW
