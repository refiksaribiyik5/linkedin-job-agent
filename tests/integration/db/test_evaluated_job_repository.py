"""SqlAlchemyEvaluatedJobRepository icin entegrasyon testleri (Roadmap M1.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from linkedinbot.db.models import AccountOrm, CompanyOrm, JobPostingOrm
from linkedinbot.db.repositories.evaluated_job_repository import (
    SqlAlchemyEvaluatedJobRepository,
)
from linkedinbot.domain.evaluated_job import (
    EvaluatedJob,
    FilterResult,
    JobStatus,
    MatchRationaleItem,
)
from linkedinbot.ports.evaluated_job_repository_port import EvaluatedJobRepositoryPort

NOW = datetime(2026, 8, 8, tzinfo=UTC)

THREE_RATIONALE_ITEMS = [
    MatchRationaleItem(component="department", value="Business Development", explanation="Eslesme"),
    MatchRationaleItem(component="location", value="Istanbul", explanation="Eslesme"),
    MatchRationaleItem(component="experience_level", value="Entry Level", explanation="Eslesme"),
]


@pytest.fixture
def job(db_session: Session, company: CompanyOrm) -> JobPostingOrm:
    orm_job = JobPostingOrm(
        job_id="linkedin-job-1",
        title="Business Development Executive",
        company_id=company.company_id,
        location_text="Istanbul",
        posted_date=NOW,
        description="Aciklama",
        application_url="https://www.linkedin.com/jobs/view/1",
        collected_at=NOW,
        content_hash="hash-1",
    )
    db_session.add(orm_job)
    db_session.flush()
    return orm_job


def _evaluated_job(account: AccountOrm, job: JobPostingOrm, **overrides) -> EvaluatedJob:
    fields = {
        "account_id": account.account_id,
        "job_id": job.job_id,
        "company_id": job.company_id,
        "status": JobStatus.NEW,
        "first_seen_at": NOW,
        "last_seen_at": NOW,
        "content_hash_at_evaluation": job.content_hash,
        "config_version_used": 1,
    }
    fields.update(overrides)
    return EvaluatedJob(**fields)


def test_repository_implements_port(db_session: Session):
    repo = SqlAlchemyEvaluatedJobRepository(db_session)
    assert isinstance(repo, EvaluatedJobRepositoryPort)


def test_create_populates_id(
    db_session: Session, account: AccountOrm, job: JobPostingOrm, make_config_profile
):
    db_session.add(make_config_profile(account.account_id))
    db_session.flush()
    repo = SqlAlchemyEvaluatedJobRepository(db_session)

    created = repo.create(_evaluated_job(account, job))

    assert created.id is not None


def test_create_and_get_round_trip_with_score_and_rationale(
    db_session: Session, account: AccountOrm, job: JobPostingOrm, make_config_profile
):
    db_session.add(make_config_profile(account.account_id))
    db_session.flush()
    repo = SqlAlchemyEvaluatedJobRepository(db_session)

    repo.create(
        _evaluated_job(
            account,
            job,
            ai_match_score=87.5,
            match_rationale=THREE_RATIONALE_ITEMS,
            department_cluster="Business Development",
            filter_result_detail={
                "location": FilterResult(passed=True, reason="Istanbul", confidence=None),
            },
        )
    )

    fetched = repo.get_by_account_and_job(account.account_id, job.job_id)

    assert fetched is not None
    assert fetched.ai_match_score == 87.5
    assert len(fetched.match_rationale) == 3
    assert fetched.match_rationale[0].component == "department"
    assert fetched.filter_result_detail["location"].reason == "Istanbul"


def test_get_by_account_and_job_returns_none_when_not_found(db_session: Session):
    repo = SqlAlchemyEvaluatedJobRepository(db_session)
    assert repo.get_by_account_and_job(uuid4(), "does-not-exist") is None


def test_update_transitions_status_new_to_seen(
    db_session: Session, account: AccountOrm, job: JobPostingOrm, make_config_profile
):
    db_session.add(make_config_profile(account.account_id))
    db_session.flush()
    repo = SqlAlchemyEvaluatedJobRepository(db_session)
    created = repo.create(_evaluated_job(account, job, status=JobStatus.NEW))

    updated = repo.update(created.model_copy(update={"status": JobStatus.SEEN}))

    assert updated.status == JobStatus.SEEN
    fetched = repo.get_by_account_and_job(account.account_id, job.job_id)
    assert fetched.status == JobStatus.SEEN


def test_update_unknown_account_and_job_raises_value_error(db_session: Session):
    repo = SqlAlchemyEvaluatedJobRepository(db_session)
    ghost = EvaluatedJob(
        account_id=uuid4(),
        job_id="does-not-exist",
        company_id="does-not-exist",
        status=JobStatus.NEW,
        first_seen_at=NOW,
        last_seen_at=NOW,
        content_hash_at_evaluation="h",
        config_version_used=1,
    )
    with pytest.raises(ValueError, match="bulunamadi"):
        repo.update(ghost)
