"""Siralama ve Gruplama - FR-11, PRD Section 16.1/16.4 (Roadmap M8.1).

Bu modul SAF fonksiyonlardan olusur (`history/diff_engine.py`, M4.2 ile
AYNI desen): hicbir repository/DB'ye erismez, dogrudan `EvaluatedJob`
(M1.1, degistirilmemis) listesi alir - is-ilani BASINA gruplama/siralama
KARARI icin gereken her sey (durum, departman kumesi, AI Match Score)
ZATEN bu domain modelinde mevcuttur.

**`group_by_department` (PRD Section 16.1):** "Departman bazli bolumler
(sadece NEW ve UPDATED ilanlar - daha once degismeden raporlanmis
ilanlar bu bolumlerde tekrar gosterilmez)." Bu yuzden yalnizca
`JobStatus.NEW`/`JobStatus.UPDATED` durumundaki ilanlar gruplanir; SEEN
(degismeden onceden raporlanmis), CLOSED ve EXCLUDED durumundaki
ilanlar HICBIR gruba dahil edilmez. `department_cluster` alani None olan
bir ilan (henuz hicbir departman eslesmesi kaydedilmemis) da HICBIR
gruba dahil edilemez - gruplanacak bir anahtari yoktur.

**`rank_top_matches` (PRD Section 16.1):** "Top Matches (AI Match
Score'a gore sirali ilk 10 ilan - acik kalan en iyi firsatlarin anlik
goruntusu; daha once raporlanmis ama hala guclu ve acik olan ilanlar
burada tekrar gorunebilir)." Bu yuzden NEW/SEEN/UPDATED HEPSI uygun
adaydir (Departman gruplarindan farkli olarak SEEN de dahildir) -
yalnizca CLOSED/EXCLUDED durumundaki ilanlar (kapanmis veya kara
listeye alinmis) haric tutulur. `ai_match_score` None olan (M7.2'nin
"Scoring Unavailable" sonucu) ilanlar, "skora gore azalan sirada
siralama" isleminin dogal bir sonucu olarak Top-N adaylarindan
CIKARILIR - bu, YENI bir dislama kurali DEGILDIR, sadece sayisal olmayan
bir degerin sayisal bir siralamaya dahil edilememesidir.

`top_n`, M6.2'nin `target_locations`/M6.4'un `confidence_threshold`
deseniyle AYNI sekilde dogrudan cagirana birakilan duz bir parametredir
- "Top Matches Sayisi" (PRD Section 17, varsayilan 10) hicbir yerde
sabit-kodlanmaz.
"""

from __future__ import annotations

from linkedinbot.domain.evaluated_job import EvaluatedJob, JobStatus

_DEPARTMENT_GROUP_STATUSES = frozenset({JobStatus.NEW, JobStatus.UPDATED})
_EXCLUDED_FROM_REPORT_STATUSES = frozenset({JobStatus.CLOSED, JobStatus.EXCLUDED})


def group_by_department(evaluated_jobs: list[EvaluatedJob]) -> dict[str, list[EvaluatedJob]]:
    groups: dict[str, list[EvaluatedJob]] = {}
    for job in evaluated_jobs:
        if job.status not in _DEPARTMENT_GROUP_STATUSES:
            continue
        if job.department_cluster is None:
            continue
        groups.setdefault(job.department_cluster, []).append(job)
    return groups


def rank_top_matches(evaluated_jobs: list[EvaluatedJob], top_n: int) -> list[EvaluatedJob]:
    candidates = [
        job
        for job in evaluated_jobs
        if job.status not in _EXCLUDED_FROM_REPORT_STATUSES and job.ai_match_score is not None
    ]
    candidates.sort(key=lambda job: job.ai_match_score, reverse=True)
    return candidates[:top_n]
