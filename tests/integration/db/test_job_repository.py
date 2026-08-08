"""SqlAlchemyJobRepository icin entegrasyon testleri (Roadmap M1.3)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from linkedinbot.db.models import CompanyOrm
from linkedinbot.db.repositories.job_repository import SqlAlchemyJobRepository
from linkedinbot.domain.job_posting import JobPosting, WorkplaceType
from linkedinbot.ports.job_repository_port import JobRepositoryPort

NOW = datetime(2026, 8, 8, tzinfo=UTC)


def _job_posting(**overrides) -> JobPosting:
    fields = {
        "job_id": "linkedin-job-1",
        "title": "Business Development Executive",
        "company_id": "test-company",
        "location": "Istanbul",
        "posted_date": NOW,
        "description": "Aciklama",
        "application_url": "https://www.linkedin.com/jobs/view/1",
        "collected_at": NOW,
        "workplace_type": WorkplaceType.HYBRID,
    }
    fields.update(overrides)
    return JobPosting(**fields)


def test_repository_implements_port(db_session: Session):
    repo = SqlAlchemyJobRepository(db_session)
    assert isinstance(repo, JobRepositoryPort)


def test_create_and_get_round_trip(db_session: Session, company: CompanyOrm):
    repo = SqlAlchemyJobRepository(db_session)

    created = repo.create(_job_posting(), content_hash="hash-1")
    fetched = repo.get_by_id("linkedin-job-1")

    assert created.job_id == "linkedin-job-1"
    assert fetched is not None
    assert fetched.title == "Business Development Executive"
    assert fetched.workplace_type == WorkplaceType.HYBRID
    assert str(fetched.application_url) == "https://www.linkedin.com/jobs/view/1"


def test_create_with_all_optional_fields_none(db_session: Session, company: CompanyOrm):
    repo = SqlAlchemyJobRepository(db_session)

    repo.create(
        _job_posting(
            job_id="linkedin-job-2",
            workplace_type=None,
            employment_type=None,
            easy_apply=None,
        ),
        content_hash="hash-2",
    )
    fetched = repo.get_by_id("linkedin-job-2")

    assert fetched.workplace_type is None
    assert fetched.employment_type is None
    assert fetched.easy_apply is None


def test_get_by_id_returns_none_when_not_found(db_session: Session):
    repo = SqlAlchemyJobRepository(db_session)
    assert repo.get_by_id("does-not-exist") is None


def test_update_changes_title(db_session: Session, company: CompanyOrm):
    repo = SqlAlchemyJobRepository(db_session)
    repo.create(_job_posting(), content_hash="hash-1")

    updated = repo.update(_job_posting(title="Yeni Baslik"), content_hash="hash-1-updated")

    assert updated.title == "Yeni Baslik"
    fetched = repo.get_by_id("linkedin-job-1")
    assert fetched.title == "Yeni Baslik"


def test_update_unknown_job_id_raises_value_error(db_session: Session, company: CompanyOrm):
    repo = SqlAlchemyJobRepository(db_session)
    with pytest.raises(ValueError, match="bulunamadi"):
        repo.update(_job_posting(job_id="does-not-exist"), content_hash="hash-x")
