"""SqlAlchemyEvaluatedJobRepository - EvaluatedJobRepositoryPort'un SQLAlchemy uygulamasi.

M1.3 review duzeltmeleri (staff-engineer incelemesinde bulunan iki hata):

1. `ai_match_score` Numeric(5,2) sutunudur; Postgres 2 ondalik basamaktan
   fazla bir deger verildiginde bunu SESSIZCE yuvarlar (hata vermez).
   `create()`/`update()` flush() sonrasi `session.refresh()` cagirmiyordu,
   bu yuzden donen domain nesnesi hala cagiranin gonderdigi
   YUVARLANMAMIS Python float'ini tasiyordu - veritabaninin fiilen
   sakladigi degerden sessizce sapan bir donus degeri. Duzeltme: flush()
   sonrasi `self._session.refresh(orm_job)` cagrilir, boylece donen
   nesne HER ZAMAN veritabaninin gercekten sakladigi (yuvarlanmis)
   degeri yansitir.
2. `update()`, `first_seen_at` dahil TUM alanlari kosulsuzca uzerine
   yaziyordu. `first_seen_at` bir ilanin bu hesap icin ilk ne zaman
   goruldugunu tasiyan, olusturulduktan sonra ASLA degismemesi gereken
   tarihsel bir alandir (AccountRepository.update()'in `created_at`'i
   ayni gerekceyle korumasiyla tutarli olarak). `update()` artik bu
   alani hic yazmaz - satirin DB'deki orijinal first_seen_at'i,
   cagiranin ne gonderdiginden bagimsiz olarak korunur.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from linkedinbot.db.models import EvaluatedJobOrm
from linkedinbot.domain.evaluated_job import EvaluatedJob, FilterResult, MatchRationaleItem
from linkedinbot.ports.evaluated_job_repository_port import EvaluatedJobRepositoryPort


def _to_domain(orm_job: EvaluatedJobOrm) -> EvaluatedJob:
    return EvaluatedJob(
        id=orm_job.id,
        account_id=orm_job.account_id,
        job_id=orm_job.job_id,
        company_id=orm_job.company_id,
        ai_match_score=(
            float(orm_job.ai_match_score) if orm_job.ai_match_score is not None else None
        ),
        match_rationale=(
            [MatchRationaleItem(**item) for item in orm_job.match_rationale]
            if orm_job.match_rationale is not None
            else None
        ),
        department_cluster=orm_job.department_cluster,
        filter_result_detail=(
            {key: FilterResult(**value) for key, value in orm_job.filter_result_detail.items()}
            if orm_job.filter_result_detail is not None
            else None
        ),
        status=orm_job.status,
        is_borderline=orm_job.is_borderline,
        first_seen_at=orm_job.first_seen_at,
        last_seen_at=orm_job.last_seen_at,
        report_appearances_count=orm_job.report_appearances_count,
        content_hash_at_evaluation=orm_job.content_hash_at_evaluation,
        config_version_used=orm_job.config_version_used,
    )


def _match_rationale_json(evaluated_job: EvaluatedJob) -> list[dict] | None:
    if evaluated_job.match_rationale is None:
        return None
    return [item.model_dump(mode="json") for item in evaluated_job.match_rationale]


def _filter_result_detail_json(evaluated_job: EvaluatedJob) -> dict | None:
    if evaluated_job.filter_result_detail is None:
        return None
    return {
        key: value.model_dump(mode="json")
        for key, value in evaluated_job.filter_result_detail.items()
    }


class SqlAlchemyEvaluatedJobRepository(EvaluatedJobRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, evaluated_job: EvaluatedJob) -> EvaluatedJob:
        orm_job = EvaluatedJobOrm(
            account_id=evaluated_job.account_id,
            job_id=evaluated_job.job_id,
            company_id=evaluated_job.company_id,
            ai_match_score=evaluated_job.ai_match_score,
            match_rationale=_match_rationale_json(evaluated_job),
            department_cluster=evaluated_job.department_cluster,
            filter_result_detail=_filter_result_detail_json(evaluated_job),
            status=evaluated_job.status,
            is_borderline=evaluated_job.is_borderline,
            first_seen_at=evaluated_job.first_seen_at,
            last_seen_at=evaluated_job.last_seen_at,
            report_appearances_count=evaluated_job.report_appearances_count,
            content_hash_at_evaluation=evaluated_job.content_hash_at_evaluation,
            config_version_used=evaluated_job.config_version_used,
        )
        if evaluated_job.id is not None:
            orm_job.id = evaluated_job.id
        self._session.add(orm_job)
        self._session.flush()
        self._session.refresh(orm_job)
        return _to_domain(orm_job)

    def get_by_account_and_job(self, account_id: UUID, job_id: str) -> EvaluatedJob | None:
        orm_job = self._session.execute(
            select(EvaluatedJobOrm).where(
                EvaluatedJobOrm.account_id == account_id, EvaluatedJobOrm.job_id == job_id
            )
        ).scalar_one_or_none()
        return _to_domain(orm_job) if orm_job is not None else None

    def list_by_account(self, account_id: UUID) -> list[EvaluatedJob]:
        orm_jobs = (
            self._session.execute(
                select(EvaluatedJobOrm).where(EvaluatedJobOrm.account_id == account_id)
            )
            .scalars()
            .all()
        )
        return [_to_domain(orm_job) for orm_job in orm_jobs]

    def update(self, evaluated_job: EvaluatedJob) -> EvaluatedJob:
        orm_job = self._session.execute(
            select(EvaluatedJobOrm).where(
                EvaluatedJobOrm.account_id == evaluated_job.account_id,
                EvaluatedJobOrm.job_id == evaluated_job.job_id,
            )
        ).scalar_one_or_none()
        if orm_job is None:
            raise ValueError(
                f"Guncellenecek degerlendirme bulunamadi: "
                f"account_id={evaluated_job.account_id}, job_id={evaluated_job.job_id}"
            )
        orm_job.company_id = evaluated_job.company_id
        orm_job.ai_match_score = evaluated_job.ai_match_score
        orm_job.match_rationale = _match_rationale_json(evaluated_job)
        orm_job.department_cluster = evaluated_job.department_cluster
        orm_job.filter_result_detail = _filter_result_detail_json(evaluated_job)
        orm_job.status = evaluated_job.status
        orm_job.is_borderline = evaluated_job.is_borderline
        # first_seen_at KASITLI OLARAK yazilmaz - bkz. modul dokumani (M1.3
        # review duzeltmesi #2). Satirin DB'deki orijinal degeri korunur.
        orm_job.last_seen_at = evaluated_job.last_seen_at
        orm_job.report_appearances_count = evaluated_job.report_appearances_count
        orm_job.content_hash_at_evaluation = evaluated_job.content_hash_at_evaluation
        orm_job.config_version_used = evaluated_job.config_version_used
        self._session.flush()
        self._session.refresh(orm_job)
        return _to_domain(orm_job)
