from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from linkedinbot.domain.company_profile import CompanyProfile


def test_valid_company_profile_with_only_identity_fields():
    company = CompanyProfile(company_id="company-1", name="Ornek A.S.")
    assert company.name == "Ornek A.S."
    assert company.industry is None
    assert company.last_evaluated_timestamp is None


def test_valid_company_profile_with_all_fields():
    company = CompanyProfile(
        company_id="company-1",
        name="Ornek A.S.",
        industry="Finans",
        employee_count_range="501-1000",
        founded_year=1998,
        last_evaluated_timestamp=datetime(2026, 8, 1, tzinfo=UTC),
    )
    assert company.founded_year == 1998


def test_missing_company_id_raises_validation_error():
    with pytest.raises(ValidationError):
        CompanyProfile(name="Ornek A.S.")


def test_missing_name_raises_validation_error():
    with pytest.raises(ValidationError):
        CompanyProfile(company_id="company-1")
