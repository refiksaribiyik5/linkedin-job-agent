"""SqlAlchemyCompanyRepository icin entegrasyon testleri (Roadmap M1.3)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from linkedinbot.db.repositories.company_repository import SqlAlchemyCompanyRepository
from linkedinbot.domain.company_profile import CompanyProfile
from linkedinbot.ports.company_repository_port import CompanyRepositoryPort


def test_repository_implements_port(db_session: Session):
    repo = SqlAlchemyCompanyRepository(db_session)
    assert isinstance(repo, CompanyRepositoryPort)


def test_create_and_get_round_trip(db_session: Session):
    repo = SqlAlchemyCompanyRepository(db_session)
    company = CompanyProfile(
        company_id="acme-corp",
        name="Acme Corp",
        industry="Technology",
        employee_count_range="51-200",
        founded_year=2010,
    )

    created = repo.create(company)
    fetched = repo.get_by_id("acme-corp")

    assert created.name == "Acme Corp"
    assert fetched is not None
    assert fetched.industry == "Technology"
    assert fetched.founded_year == 2010


def test_create_with_only_identity_fields(db_session: Session):
    # Section 12.3: sirket hakkinda yeterli veri bulunamayabilir ("Unrated").
    repo = SqlAlchemyCompanyRepository(db_session)
    repo.create(CompanyProfile(company_id="unrated-co", name="Unrated Co"))

    fetched = repo.get_by_id("unrated-co")

    assert fetched.industry is None
    assert fetched.employee_count_range is None
    assert fetched.founded_year is None


def test_get_by_id_returns_none_when_not_found(db_session: Session):
    repo = SqlAlchemyCompanyRepository(db_session)
    assert repo.get_by_id("does-not-exist") is None


def test_update_changes_industry(db_session: Session):
    repo = SqlAlchemyCompanyRepository(db_session)
    repo.create(CompanyProfile(company_id="acme-corp", name="Acme Corp", industry="Retail"))

    updated = repo.update(
        CompanyProfile(company_id="acme-corp", name="Acme Corp", industry="Technology")
    )

    assert updated.industry == "Technology"
    fetched = repo.get_by_id("acme-corp")
    assert fetched.industry == "Technology"
