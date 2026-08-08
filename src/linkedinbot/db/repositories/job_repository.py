"""SqlAlchemyJobRepository - JobRepositoryPort'un SQLAlchemy uygulamasi.

`content_hash` neden ayri bir parametre olarak alinir: bkz.
ports/job_repository_port.py modul dokumani.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from linkedinbot.db.models import JobPostingOrm
from linkedinbot.domain.job_posting import JobPosting
from linkedinbot.ports.job_repository_port import JobRepositoryPort


def _to_domain(orm_job: JobPostingOrm) -> JobPosting:
    return JobPosting(
        job_id=orm_job.job_id,
        title=orm_job.title,
        company_id=orm_job.company_id,
        location=orm_job.location_text,
        posted_date=orm_job.posted_date,
        description=orm_job.description,
        application_url=orm_job.application_url,
        collected_at=orm_job.collected_at,
        workplace_type=orm_job.workplace_type,
        employment_type=orm_job.employment_type,
        easy_apply=orm_job.easy_apply,
    )


class SqlAlchemyJobRepository(JobRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, job_posting: JobPosting, content_hash: str) -> JobPosting:
        orm_job = JobPostingOrm(
            job_id=job_posting.job_id,
            title=job_posting.title,
            company_id=job_posting.company_id,
            location_text=job_posting.location,
            workplace_type=job_posting.workplace_type,
            posted_date=job_posting.posted_date,
            description=job_posting.description,
            employment_type=job_posting.employment_type,
            easy_apply=job_posting.easy_apply,
            application_url=str(job_posting.application_url),
            collected_at=job_posting.collected_at,
            content_hash=content_hash,
        )
        self._session.add(orm_job)
        self._session.flush()
        return _to_domain(orm_job)

    def get_by_id(self, job_id: str) -> JobPosting | None:
        orm_job = self._session.get(JobPostingOrm, job_id)
        return _to_domain(orm_job) if orm_job is not None else None

    def update(self, job_posting: JobPosting, content_hash: str) -> JobPosting:
        orm_job = self._session.get(JobPostingOrm, job_posting.job_id)
        if orm_job is None:
            raise ValueError(f"Guncellenecek ilan bulunamadi: {job_posting.job_id}")
        orm_job.title = job_posting.title
        orm_job.company_id = job_posting.company_id
        orm_job.location_text = job_posting.location
        orm_job.workplace_type = job_posting.workplace_type
        orm_job.posted_date = job_posting.posted_date
        orm_job.description = job_posting.description
        orm_job.employment_type = job_posting.employment_type
        orm_job.easy_apply = job_posting.easy_apply
        orm_job.application_url = str(job_posting.application_url)
        orm_job.collected_at = job_posting.collected_at
        orm_job.content_hash = content_hash
        self._session.flush()
        return _to_domain(orm_job)
