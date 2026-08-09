"""History/Diff Engine (Roadmap M4.2, FR-8/FR-9/FR-10/FR-14).

TDD Section 6 modul sorumluluklari tablosu: `history` modulu "Her
JobPosting'i geçmişle karşılaştırıp New/Seen/Updated/Closed durumuna
atar." TDD Section 8 Veri Akisi tablosu, bu pipeline adiminin (5 -
Historical Cross-Reference) ciktisini acikca `(JobPosting, Status)[]`
olarak tanimlar - `EvaluatedJob[]` DEGIL. TDD Section 8'in "eager cache
write, atomic state commit" ayrimi da bunu dogrular: `evaluated_jobs.status`
yalnizca pipeline'in 11. adiminda (State Update, Orchestrator'in isi,
Roadmap M9.2 - henuz insa edilmedi) TEK bir DB transaction'inda commit
edilir. Bu yuzden bu modul (M4.1'in normalizer.py'siyle AYNI desende)
KASITLI OLARAK SAF bir fonksiyondur:

- HICBIR repository/DB'ye ERISMEZ (ne `JobRepositoryPort` ne
  `EvaluatedJobRepositoryPort` import edilir/cagrilir) - proje
  talimatiyla acikca onaylanan mimari karar.
- "Gecmis kayitlar" (`previous_evaluations`), cagiran (henuz insa
  edilmemis bir Orchestrator, M9) tarafindan acikca bir parametre olarak
  verilir; bu modul kendisi hicbir sekilde veri OKUMAZ/YAZMAZ.

Durum makinesi (TDD Section 17): `New -> Seen`; `Seen -> Updated` (FR-14
anlamli degisiklik) `-> Seen`; `Seen/Updated -> Closed`; `Closed -> New`
(yeniden acilma, EDGE-5). `Excluded` (Filtreleme'nin, Faz 6'nin kendi
kavrami) bu durum makinesinin bir parcasi DEGILDIR - M4.2 onu ne uretir
ne de ozel olarak ele alir; `previous_evaluations`'ta rastlanirsa CLOSED
disi herhangi bir durum gibi (icerik karsilastirmasiyla) islenir.

Ayni taramada TEKRARLANAN `job_id` (bkz. modul ici not - M3.3'un ic-
denetiminde tespit edilen, kabul edilmis bir risk: ortusen departman
aramalari ayni gercek ilani birden fazla kez toplayabilir) TEK bir
sonuca indirgenir - TDD Appendix'in "history.diff_engine ... Duplicate
... tespiti" (FR-8) atfinin dogrudan karsiligidir.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from linkedinbot.domain.evaluated_job import JobStatus
from linkedinbot.domain.job_posting import JobPosting
from linkedinbot.history.content_hasher import has_content_changed


class PreviousEvaluation(BaseModel):
    """Bir hesabin bir ilan icin bilinen EN SON durumu - `evaluated_jobs`
    tablosunun (M1.3) ilgili iki alaninin (status, content_hash_at_evaluation)
    saf-veri (DB'siz) bir yansimasidir. Cagiran, bu veriyi
    `EvaluatedJobRepositoryPort`'tan (M1.3) okuyup buraya besler - bu
    modulun kendisi o Port'u hic import etmez.
    """

    model_config = ConfigDict(extra="forbid")

    status: JobStatus
    content_hash: str


def _assign_status(previous: PreviousEvaluation | None, content_hash: str) -> JobStatus:
    if previous is None:
        return JobStatus.NEW
    if previous.status == JobStatus.CLOSED:
        return JobStatus.NEW
    if has_content_changed(previous.content_hash, content_hash):
        return JobStatus.UPDATED
    return JobStatus.SEEN


def diff_job_postings(
    current_scan: list[tuple[JobPosting, str]],
    previous_evaluations: dict[str, PreviousEvaluation],
) -> tuple[list[tuple[JobPosting, JobStatus]], list[str]]:
    """Bu taramada gorulen her ilana New/Seen/Updated durumunu atar ve
    ONCEDEN aktif olup bu taramada artik gorunmeyen ilanlarin job_id'lerini
    (Closed) ayri olarak doner.

    Doner: `(sonuclar, kapanmis_job_id_listesi)` - `sonuclar`,
    `current_scan`'daki HER benzersiz `job_id` icin TAM OLARAK bir
    `(JobPosting, JobStatus)` cifti icerir (ayni taramada tekrarlanan
    `job_id`'ler ilk gorulen haliyle TEK bir sonuca indirgenir); `kapanmis_job_id_listesi`,
    `previous_evaluations`'ta CLOSED-disi bir durumla kayitli olup bu
    taramada HIC gorunmeyen `job_id`'leri icerir (zaten Closed olarak
    bilinen bir ilan, hala goriunmuyor diye TEKRAR bu listeye eklenmez).
    """
    results: list[tuple[JobPosting, JobStatus]] = []
    seen_job_ids: set[str] = set()

    for job_posting, content_hash in current_scan:
        if job_posting.job_id in seen_job_ids:
            continue
        seen_job_ids.add(job_posting.job_id)

        previous = previous_evaluations.get(job_posting.job_id)
        results.append((job_posting, _assign_status(previous, content_hash)))

    newly_closed_job_ids = [
        job_id
        for job_id, previous in previous_evaluations.items()
        if previous.status != JobStatus.CLOSED and job_id not in seen_job_ids
    ]

    return results, newly_closed_job_ids
