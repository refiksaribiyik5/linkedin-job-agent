"""Rapor Derleyici - FR-11, FR-20, PRD Section 16 (Roadmap M8.2).

Bu modul SAF bir fonksiyon seklinde tasarlanmistir (`ranking/ranker.py`,
M8.1 ile AYNI desen): hicbir dosyaya/DB'ye yazmaz, yalnizca bellek-ici bir
Markdown metni doner - kalicilik (ReportRepositoryPort'a yazma, reports
tablosuna satir ekleme, run_id ile idempotency kontrolu) TDD Section
18'in kendi akis tanimi geregi acikca M8.3'un isidir (bu modul TDD'nin
1-2 ve 6. adimlarini kapsar, 3-5. adimlarini KAPSAMAZ).

**Kullanicinin M8.2 durdurma-ve-karar surecinde verdigi ACIK KARARLAR:**
- `JobPosting` verisi (title/location/posted_date/easy_apply/
  application_url), enjekte edilen `JobRepositoryPort` (M1.3,
  degistirilmemis) uzerinden HER ilan icin ayri ayri `.get_by_id()`
  cagrilarak alinir - onceden hazirlanmis bir dict PARAMETRE OLARAK
  KABUL EDILMEZ.
- Company Quality Score, `match_rationale`'dan ASLA ayristirilmaz (bu,
  projenin tipli-domain yaklasimini ihlal ederdi); bunun yerine
  cagiranin (gelecekteki orkestrasyon katmani) ZATEN hesaplamis oldugu
  `company_scores_by_id: dict[str, CompanyScore]` (M7.1'in `CompanyScore`
  degismeden kullanilir) lookup'i uzerinden alinir.
- `CompanyRepositoryPort` KULLANILMAZ - `normalizer.py` (M4.1,
  degistirilmemis) konvansiyonu geregi `EvaluatedJob.company_id` ZATEN
  ham taranan sirket goruntu adidir; ayrica bir sirket-adi lookup'ina
  gerek yoktur.

**Diger tasarim kararlari (Roadmap/PRD/TDD'den dogal sonuc, escalasyon
gerektirmeyen):**
- Siralama/gruplama, M8.1'in `group_by_department`/`rank_top_matches`'i
  (degistirilmemis) DOGRUDAN, ham/filtrelenmemis `evaluated_jobs` girdisi
  uzerinde cagrilarak yapilir - bu modul kendi siralama/filtreleme
  mantigini TEKRARLAMAZ.
- `ai_match_score`i None olan (M7.2'nin "Scoring Unavailable" sonucu) bir
  ilan RENDER EDILMEZ: FR-11 "her girdi ... gerekce blogunu icerir" der,
  ancak boyle bir ilanin `match_rationale`'i de zorunlu olarak None'dir
  (`EvaluatedJob`'un kendi validatoru, FR-7) - gosterilecek gecerli bir
  gerekce yoktur. `rank_top_matches` bu filtrelemeyi zaten dogal olarak
  yapar (skora gore siralama); `group_by_department` YAPMAZ (M8.1'in
  kendi kapsami disidir), bu yuzden bu modul departman gruplarini ayrica
  filtreler.
- "Previously Reported" (PRD Section 16.1/16.3), `EvaluatedJob.
  report_appearances_count > 0 AND status == SEEN` ile tespit edilir -
  `ReportRepositoryPort`'un hesap-capinda toplu bir "tum raporlari
  listele" metodu YOKTUR (yalnizca tekli ID/run_id sorgulari), bu yuzden
  gecmis raporlari toplu sorgulamak ne mumkun ne gereklidir; alan ZATEN
  M1.1'de mevcuttur ve gelecekteki orkestratorun "State Update" adimi
  tarafindan bakimi yapilir. `report_appearances_count == 0` olan bir
  SEEN ilan (orn. esik/Top-N degisikligi nedeniyle YENI uygun hale
  gelmis) "Previously Reported" olarak ETIKETLENMEZ - hicbir onceki
  raporda GERCEKTEN gorunmedigi icin bu, GERCEK OLMAYAN bir iddia
  olurdu; bu durumda ilan hicbir ek not olmadan gosterilir.
  **Render bicimi (self-review sirasinda cozulen PRD-ici catiskisi):**
  Section 16.1 bu ilanlarin "acikca 'Previously Reported' olarak
  isaretlenerek" gosterilmesini ister, ancak Section 16.3'un etiketleme
  tablosu AYNI durum icin "Etiketsiz" (Untagged) der - bu iki ifade
  birebir okundugunda celisir. Kullaniciya sorulup ACIKCA karar
  verildi: [NEW]/[UPDATED] ile AYNI onek-parantez ("bracket") kuralı
  KULLANILMAZ (boylece 16.3'un "Etiketsiz" sozcugu, bracket-tag
  sozlugune gore dogru kalir), ama "Previously Reported" sozcukleri
  BASLIGIN SONUNA bir not olarak eklenir (boylece 16.1'in "acikca
  isaretlenerek" sarti da saglanir). Bkz. `_bracket_tag`/
  `_is_previously_reported`/`_heading`.
- Bootstrap (FR-20, EDGE-13): `is_bootstrap`, dogrudan cagirana birakilan
  duz bir `bool` parametredir (gelecekteki orkestrator, `run_logs`
  gecmisinin bos olup olmadigini ZATEN bilir) - bu modul bu KONTROL icin
  ayrica bir `RunLogRepositoryPort` enjekte etmez/sorgulamaz. Bootstrap
  modunda NEW olarak nitelenecek ilanlar "[Bootstrap]" ile etiketlenir
  (TDD Section 18: "normal NEW bolumleri yerine ayri bir Bootstrap/Ilk
  Tarama bolumu render edilir") ve ozet satiri farkli bir metin kullanir.
- Eksik lookup'lar (JobRepositoryPort'ta bulunamayan bir job_id, veya
  company_scores_by_id'de eksik bir company_id) YUKSEK SESLE basarisiz
  olur (ValueError) - bu, GECERLI bir "Unrated" CompanyScore'dan
  (anahtar MEVCUT ama score_total None) FARKLIDIR; "Unrated" PRD
  12.3 geregi duz metin olarak gosterilir, hata degildir.
"""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import TYPE_CHECKING

from linkedinbot.domain.evaluated_job import JobStatus
from linkedinbot.ranking.ranker import group_by_department, rank_top_matches

if TYPE_CHECKING:
    from datetime import date

    from linkedinbot.domain.evaluated_job import EvaluatedJob
    from linkedinbot.domain.job_posting import JobPosting
    from linkedinbot.ports.job_repository_port import JobRepositoryPort
    from linkedinbot.scoring.company_scoring import CompanyScore

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "markdown_report.template.md"

_NO_TOP_MATCHES_TEXT = "_No open matches found._"
_NO_DEPARTMENT_SECTIONS_TEXT = "_No new or updated postings in any department._"


def _company_quality_score(
    company_id: str, company_scores_by_id: dict[str, CompanyScore]
) -> CompanyScore:
    if company_id not in company_scores_by_id:
        raise ValueError(
            f"company_scores_by_id has no CompanyScore entry for company_id={company_id!r}."
        )
    return company_scores_by_id[company_id]


def _job_posting(job: EvaluatedJob, job_repository: JobRepositoryPort) -> JobPosting:
    posting = job_repository.get_by_id(job.job_id)
    if posting is None:
        raise ValueError(f"JobRepositoryPort has no JobPosting for job_id={job.job_id!r}.")
    return posting


def _bracket_tag(job: EvaluatedJob, is_bootstrap: bool) -> str | None:
    if job.status == JobStatus.NEW:
        return "Bootstrap" if is_bootstrap else "NEW"
    if job.status == JobStatus.UPDATED:
        return "UPDATED"
    return None


def _is_previously_reported(job: EvaluatedJob) -> bool:
    return job.status == JobStatus.SEEN and job.report_appearances_count > 0


def _heading(job: EvaluatedJob, title: str, company_id: str, is_bootstrap: bool) -> str:
    bracket = _bracket_tag(job, is_bootstrap)
    prefix = f"[{bracket}] " if bracket else ""
    suffix = " (Previously Reported)" if _is_previously_reported(job) else ""
    return f"{prefix}{title} — {company_id}{suffix}"


def _render_top_match_line(
    index: int,
    job: EvaluatedJob,
    job_repository: JobRepositoryPort,
    company_scores_by_id: dict[str, CompanyScore],
    is_bootstrap: bool,
) -> str:
    posting = _job_posting(job, job_repository)
    company_score = _company_quality_score(job.company_id, company_scores_by_id)
    company_quality = (
        "Unrated" if company_score.score_total is None else f"{company_score.score_total:.0f}"
    )
    heading = _heading(job, posting.title, job.company_id, is_bootstrap)
    return (
        f"{index}. {heading} "
        f"(AI Match: {job.ai_match_score:.0f} / Company Quality: {company_quality})"
    )


def _render_department_entry(
    job: EvaluatedJob,
    job_repository: JobRepositoryPort,
    company_scores_by_id: dict[str, CompanyScore],
    is_bootstrap: bool,
) -> str:
    posting = _job_posting(job, job_repository)
    company_score = _company_quality_score(job.company_id, company_scores_by_id)
    heading = _heading(job, posting.title, job.company_id, is_bootstrap)

    location = posting.location
    if posting.workplace_type is not None:
        location = f"{location} ({posting.workplace_type.value})"

    quality_line = (
        "Unrated" if company_score.score_total is None else f"{company_score.score_total:.0f} / 100"
    )

    easy_apply = "N/A" if posting.easy_apply is None else ("Yes" if posting.easy_apply else "No")

    bullet_lines = "\n".join(f"- {item.explanation}" for item in job.match_rationale)

    return (
        f"### {heading}\n"
        f"- Location: {location}\n"
        f"- Posted Date: {posting.posted_date:%Y-%m-%d}\n"
        f"- AI Match Score: {job.ai_match_score:.0f} / 100\n"
        f"- Company Quality Score: {quality_line}\n"
        f"- Easy Apply: {easy_apply}\n"
        f"- Application Link: [Apply]({posting.application_url})\n"
        f"\n"
        f"Selected because:\n"
        f"{bullet_lines}"
    )


def _summary_line(evaluated_jobs: list[EvaluatedJob], is_bootstrap: bool) -> str:
    if is_bootstrap:
        return (
            "**Bootstrap Run — Initial Inventory.** This is the first run; all discovered "
            "postings below represent the initial scan, not newly-posted jobs."
        )
    new_count = sum(1 for job in evaluated_jobs if job.status == JobStatus.NEW)
    return f"**Total new postings: {new_count}**"


def compile_report(
    evaluated_jobs: list[EvaluatedJob],
    job_repository: JobRepositoryPort,
    company_scores_by_id: dict[str, CompanyScore],
    top_n: int,
    run_date: date,
    is_bootstrap: bool,
) -> str:
    """FR-11/FR-20/PRD Section 16'ya uygun bir Markdown rapor metni derler.

    Kalicilik (dosyaya/DB'ye yazma) icermez - M8.3'un isidir (TDD Section
    18, adim 3-5). `job_repository` ve `company_scores_by_id`, cagiranin
    (gelecekteki orkestrasyon katmani) ZATEN sahip oldugu artifact'lardir.
    """
    template = Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))

    top_matches = rank_top_matches(evaluated_jobs, top_n)
    if top_matches:
        top_matches_section = "\n".join(
            _render_top_match_line(index, job, job_repository, company_scores_by_id, is_bootstrap)
            for index, job in enumerate(top_matches, start=1)
        )
    else:
        top_matches_section = _NO_TOP_MATCHES_TEXT

    department_groups = group_by_department(evaluated_jobs)
    department_groups = {
        name: [job for job in jobs if job.ai_match_score is not None]
        for name, jobs in department_groups.items()
    }
    department_groups = {name: jobs for name, jobs in department_groups.items() if jobs}

    if department_groups:
        department_blocks = [
            "## {name}\n\n{entries}".format(
                name=name,
                entries="\n\n".join(
                    _render_department_entry(
                        job, job_repository, company_scores_by_id, is_bootstrap
                    )
                    for job in jobs
                ),
            )
            for name, jobs in department_groups.items()
        ]
        department_sections = "\n\n".join(department_blocks)
    else:
        department_sections = _NO_DEPARTMENT_SECTIONS_TEXT

    return template.substitute(
        run_date=run_date.isoformat(),
        summary_line=_summary_line(evaluated_jobs, is_bootstrap),
        top_matches_section=top_matches_section,
        department_sections=department_sections,
    )
