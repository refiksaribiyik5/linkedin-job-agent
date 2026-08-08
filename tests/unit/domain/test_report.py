from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from linkedinbot.domain.report import Report


def _base_fields(**overrides):
    fields = {
        "report_id": uuid4(),
        "account_id": uuid4(),
        "generated_at": datetime(2026, 8, 7, tzinfo=UTC),
        "config_snapshot_ref": "1",
        "storage_path": "reports/some-account/2026-08-07_report.md",
    }
    fields.update(overrides)
    return fields


def test_valid_report_defaults_to_markdown_format():
    report = Report(**_base_fields())
    assert report.format == "Markdown"
    assert report.included_job_ids == []
    assert report.top_matches == []
    assert isinstance(report.storage_path, Path)


def test_top_matches_is_not_hardcoded_to_ten():
    # Section 17: "Top Matches Sayisi" konfigure edilebilir bir parametredir
    # (varsayilan 10, 15'e vb. degistirilebilir); domain modeli bu sayiyi
    # sabit bir kural olarak dayatmamalidir.
    fifteen_ids = [f"linkedin-{i}" for i in range(15)]
    report = Report(**_base_fields(top_matches=fifteen_ids))
    assert len(report.top_matches) == 15


def test_missing_storage_path_raises_validation_error():
    fields = {k: v for k, v in _base_fields().items() if k != "storage_path"}
    with pytest.raises(ValidationError):
        Report(**fields)


def test_missing_config_snapshot_ref_raises_validation_error():
    fields = {k: v for k, v in _base_fields().items() if k != "config_snapshot_ref"}
    with pytest.raises(ValidationError):
        Report(**fields)
