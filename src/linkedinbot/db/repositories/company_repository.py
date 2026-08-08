"""SqlAlchemyCompanyRepository - CompanyRepositoryPort'un SQLAlchemy uygulamasi.

`first_seen_at`/`last_updated_at` yonetimi icin bkz.
ports/company_repository_port.py modul dokumani.

`last_evaluated_timestamp` reddi (M1.3 review duzeltmesi): `companies`
tablosunda bu alana karsilik gelen hicbir sutun yoktur (bkz. Port modul
dokumani - skorlamayla ilgili her sey `company_scores`'a, M7.1'e aittir).
Ilk implementasyon bu alani `CompanyProfile`den okumuyordu bile - eger
bir cagiran onu doldurup gonderirse, deger sessizce yok oluyordu (gercek
bir silent-data-loss yolu). Duzeltme: bu alan doluysa `create()`/`update()`
acikca ve yuksek sesle reddeder; sessizce yutmak yerine cagirana hemen
"bu alan henuz kalici degil" bilgisini verir.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from linkedinbot.db.models import CompanyOrm
from linkedinbot.domain.company_profile import CompanyProfile
from linkedinbot.ports.company_repository_port import CompanyRepositoryPort

_LAST_EVALUATED_TIMESTAMP_NOT_PERSISTED = (
    "CompanyProfile.last_evaluated_timestamp henuz hicbir sutuna karsilik "
    "gelmiyor (bkz. company_repository_port.py modul dokumani - bu alan "
    "kavramsal olarak company_scores'a, M7.1'e aittir). Bu alani None "
    "birakmadan kalici hale getirmeye calismak sessizce veri kaybina yol "
    "acardi; bu yuzden acikca reddedilir."
)


def _to_domain(orm_company: CompanyOrm) -> CompanyProfile:
    return CompanyProfile(
        company_id=orm_company.company_id,
        name=orm_company.name,
        industry=orm_company.industry,
        employee_count_range=orm_company.employee_count_range,
        founded_year=orm_company.founded_year,
    )


class SqlAlchemyCompanyRepository(CompanyRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, company: CompanyProfile) -> CompanyProfile:
        if company.last_evaluated_timestamp is not None:
            raise ValueError(_LAST_EVALUATED_TIMESTAMP_NOT_PERSISTED)
        now = datetime.now(UTC)
        orm_company = CompanyOrm(
            company_id=company.company_id,
            name=company.name,
            industry=company.industry,
            employee_count_range=company.employee_count_range,
            founded_year=company.founded_year,
            first_seen_at=now,
            last_updated_at=now,
        )
        self._session.add(orm_company)
        self._session.flush()
        return _to_domain(orm_company)

    def get_by_id(self, company_id: str) -> CompanyProfile | None:
        orm_company = self._session.get(CompanyOrm, company_id)
        return _to_domain(orm_company) if orm_company is not None else None

    def update(self, company: CompanyProfile) -> CompanyProfile:
        if company.last_evaluated_timestamp is not None:
            raise ValueError(_LAST_EVALUATED_TIMESTAMP_NOT_PERSISTED)
        orm_company = self._session.get(CompanyOrm, company.company_id)
        if orm_company is None:
            raise ValueError(f"Guncellenecek sirket bulunamadi: {company.company_id}")
        orm_company.name = company.name
        orm_company.industry = company.industry
        orm_company.employee_count_range = company.employee_count_range
        orm_company.founded_year = company.founded_year
        orm_company.last_updated_at = datetime.now(UTC)
        self._session.flush()
        return _to_domain(orm_company)
