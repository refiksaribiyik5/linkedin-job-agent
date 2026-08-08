from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from linkedinbot.domain.job_posting import JobPosting, WorkplaceType

VALID_MINIMUM_FIELDS = {
    "job_id": "linkedin-123",
    "title": "Business Development Executive",
    "company_id": "company-1",
    "location": "Istanbul, Turkiye",
    "posted_date": datetime(2026, 8, 1, tzinfo=UTC),
    "description": "Ornek is ilani aciklamasi.",
    "application_url": "https://www.linkedin.com/jobs/view/123",
    "collected_at": datetime(2026, 8, 7, tzinfo=UTC),
}


def test_valid_job_posting_with_only_fr2_minimum_fields():
    job = JobPosting(**VALID_MINIMUM_FIELDS)
    assert job.job_id == "linkedin-123"
    assert job.workplace_type is None
    assert job.employment_type is None
    assert job.easy_apply is None


def test_valid_job_posting_with_all_fields():
    job = JobPosting(
        **VALID_MINIMUM_FIELDS,
        workplace_type=WorkplaceType.HYBRID,
        employment_type="Tam zamanli",
        easy_apply=True,
    )
    assert job.workplace_type == WorkplaceType.HYBRID
    assert job.easy_apply is True


@pytest.mark.parametrize("missing_field", list(VALID_MINIMUM_FIELDS))
def test_missing_fr2_minimum_field_raises_validation_error(missing_field):
    fields = {k: v for k, v in VALID_MINIMUM_FIELDS.items() if k != missing_field}
    with pytest.raises(ValidationError):
        JobPosting(**fields)


def test_invalid_application_url_raises_validation_error():
    fields = {**VALID_MINIMUM_FIELDS, "application_url": "not-a-url"}
    with pytest.raises(ValidationError):
        JobPosting(**fields)


def test_workplace_type_accepts_plain_string_matching_prd_value():
    job = JobPosting(**VALID_MINIMUM_FIELDS, workplace_type="On-site")
    assert job.workplace_type is WorkplaceType.ON_SITE


def test_invalid_workplace_type_raises_validation_error():
    with pytest.raises(ValidationError):
        JobPosting(**VALID_MINIMUM_FIELDS, workplace_type="Underwater")
