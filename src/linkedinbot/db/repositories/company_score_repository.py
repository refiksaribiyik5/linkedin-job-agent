"""SqlAlchemyCompanyScoreRepository - CompanyScoreRepositoryPort'un
SQLAlchemy uygulamasi (Roadmap M9.2).

`CompanyScoreOrm.company_id`'nin `companies` tablosuna bir FOREIGN KEY
tasidigi (M1.2) icin, bir `CompanyScore` ancak karsilik gelen bir
`CompanyOrm` satiri zaten varsa olusturulabilir - bu, repository
tarafindan ayrica dogrulanmaz, DB'nin kendi kisiti tarafindan
uygulanir (diger repository'lerdeki FK alanlariyla AYNI yaklasim,
orn. `ReportOrm.run_id`).

`score_total` neden `float(...)`'a ACIKCA cevrilir VE her `create()`/
`update()` sonrasi `session.refresh()` cagrilir: `db/repositories/
evaluated_job_repository.py`'nin (M1.3 review duzeltmesi) BIREBIR AYNI
deseni - `CompanyScoreOrm.score_total`, `EvaluatedJobOrm.ai_match_score`
ile AYNI `Numeric(5, 2)` sutun tipini kullanir. Postgres, 2 ondalik
basamaktan fazla bir deger verildiginde bunu SESSIZCE yuvarlar (hata
vermez); `refresh()` cagrilmazsa donen domain nesnesi DB'nin fiilen
sakladigi (yuvarlanmis) degeri degil, cagiranin gonderdigi ham degeri
tasir - veritabanindan sessizce sapan bir donus degeri olurdu. Ayrica
psycopg, `Numeric` sutunlarini Python `float` DEGIL `decimal.Decimal`
olarak doner; `CompanyScore.score_total: float | None` alanina uymasi
icin acik bir `float(...)` donusumu gerekir.

`score_breakdown`, `CompanyScoreOrm` uzerinde nullable bir JSONB
sutunudur, ama `CompanyScore.score_breakdown: dict[str, float | None]`
Optional DEGILDIR (bkz. `scoring/company_scoring.py`, M7.1 -
"Unrated" durumunda bile `score_total=None` ile birlikte
`score_breakdown={}` doner, `None` degil). Okurken NULL -> `{}`
donusumu bu yuzden gereklidir.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from linkedinbot.db.models import CompanyScoreOrm
from linkedinbot.ports.company_score_repository_port import CompanyScoreRepositoryPort
from linkedinbot.scoring.company_scoring import CompanyScore


def _to_domain(orm_score: CompanyScoreOrm) -> CompanyScore:
    return CompanyScore(
        company_id=orm_score.company_id,
        weight_profile_id=orm_score.weight_profile_id,
        rubric_version=orm_score.rubric_version,
        score_total=(
            float(orm_score.score_total) if orm_score.score_total is not None else None
        ),
        score_breakdown=(
            orm_score.score_breakdown if orm_score.score_breakdown is not None else {}
        ),
        evaluated_at=orm_score.evaluated_at,
    )


def _find(
    session: Session, company_id: str, weight_profile_id: UUID | None, rubric_version: int
) -> CompanyScoreOrm | None:
    return session.execute(
        select(CompanyScoreOrm).where(
            CompanyScoreOrm.company_id == company_id,
            CompanyScoreOrm.weight_profile_id == weight_profile_id,
            CompanyScoreOrm.rubric_version == rubric_version,
        )
    ).scalar_one_or_none()


class SqlAlchemyCompanyScoreRepository(CompanyScoreRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, company_score: CompanyScore) -> CompanyScore:
        orm_score = CompanyScoreOrm(
            company_id=company_score.company_id,
            weight_profile_id=company_score.weight_profile_id,
            rubric_version=company_score.rubric_version,
            score_total=company_score.score_total,
            score_breakdown=company_score.score_breakdown,
            evaluated_at=company_score.evaluated_at,
        )
        self._session.add(orm_score)
        self._session.flush()
        self._session.refresh(orm_score)
        return _to_domain(orm_score)

    def get_by_key(
        self, company_id: str, weight_profile_id: UUID | None, rubric_version: int
    ) -> CompanyScore | None:
        orm_score = _find(self._session, company_id, weight_profile_id, rubric_version)
        return _to_domain(orm_score) if orm_score is not None else None

    def update(self, company_score: CompanyScore) -> CompanyScore:
        orm_score = _find(
            self._session,
            company_score.company_id,
            company_score.weight_profile_id,
            company_score.rubric_version,
        )
        if orm_score is None:
            raise ValueError(
                "Guncellenecek sirket skoru bulunamadi: "
                f"company_id={company_score.company_id}, "
                f"weight_profile_id={company_score.weight_profile_id}, "
                f"rubric_version={company_score.rubric_version}"
            )
        orm_score.score_total = company_score.score_total
        orm_score.score_breakdown = company_score.score_breakdown
        orm_score.evaluated_at = company_score.evaluated_at
        self._session.flush()
        self._session.refresh(orm_score)
        return _to_domain(orm_score)
