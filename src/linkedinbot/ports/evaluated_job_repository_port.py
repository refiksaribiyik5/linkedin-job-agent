"""EvaluatedJobRepositoryPort - evaluated_jobs tablosu icin soyut arayuz.

evaluated_jobs bir Account-Scoped tablodur (PRD Section 15.0). Domain
kimligi `(account_id, job_id)` ciftidir (DB'nin kendisi de
`uq_evaluated_jobs_account_job` ile bunu dogrular - bkz. db/models.py);
surrogate `id` alani yalnizca DB-ici bir PK'dir ve sorgu/guncelleme
anahtarı olarak kullanilmaz (bkz. domain/evaluated_job.py modul
dokumani). `create`/`update` metodlari `EvaluatedJob` nesnesinin
`account_id` alanini zaten zorunlu tuttugu icin (Pydantic dogrulamasi),
account_id parametresi olmadan cagrilmalari yapisal olarak imkansizdir
(TDD Section 14).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from linkedinbot.domain.evaluated_job import EvaluatedJob


class EvaluatedJobRepositoryPort(ABC):
    """evaluated_jobs tablosu icin temel create/read/update islemleri (Roadmap M1.3)."""

    @abstractmethod
    def create(self, evaluated_job: EvaluatedJob) -> EvaluatedJob:
        """Yeni bir degerlendirme satiri olusturur; donen nesnenin `id`
        alani DB tarafindan uretilmis surrogate anahtarla doldurulmus olur.
        """

    @abstractmethod
    def get_by_account_and_job(self, account_id: UUID, job_id: str) -> EvaluatedJob | None:
        """Kayit bulunamazsa None doner."""

    @abstractmethod
    def update(self, evaluated_job: EvaluatedJob) -> EvaluatedJob:
        """`(evaluated_job.account_id, evaluated_job.job_id)` ciftiyle var
        olan satiri gunceller (orn. History/Diff Engine'in M4.2'de
        durumu New -> Seen yapmasi).
        """
