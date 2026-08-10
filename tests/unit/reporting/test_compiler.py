"""reporting/compiler.py icin birim testleri (Roadmap M8.2, FR-11, FR-20,
PRD Section 16).

Roadmap M8.2 "Beklenen Sonuc": "Sabit bir fixture'dan PRD Section
16.2'nin iskeletine uyan gercek bir Markdown ciktisi uretilir."
"Tamamlanma Dogrulamasi": "Golden-file testi - ciktinin, onceden
onaylanmis beklenen bir Markdown dosyasiyla farki olmadigi dogrulanir;
bos gecmis fixture'iyla Bootstrap dalinin tetiklendigi ayrica
dogrulanir."

Proje talimatiyla acikca onaylanan mimari kararlar (kullanicinin M8.2
durdurma-ve-karar surecinde verdigi ACIK KARARLAR):
- `compile_report()`, `JobRepositoryPort` (M1.3, degistirilmemis) enjekte
  edilen bir bagimlilik olarak alir ve HER ilan icin `.get_by_id()`
  cagirir - JobPosting verisi (title/location/posted_date/easy_apply/
  application_url) TAM OLARAK bu Port uzerinden gelir.
- Company Quality Score, M7.1'in `CompanyScore`'unu (degistirilmemis)
  ZATEN-HESAPLANMIS bir artifact olarak `company_scores_by_id: dict[str,
  CompanyScore]` lookup'i uzerinden alir - `match_rationale`'dan
  AYRISTIRILMAZ (bu, projenin tipli-domain yaklasimini ihlal ederdi).
  `CompanyRepositoryPort` KULLANILMAZ - `company_id` zaten `normalizer.py`
  (M4.1) tarafindan kurulmus "ham taranan sirket adi = company_id"
  kongvansiyonu geregi goruntu adi olarak DOGRUDAN kullanilir.
- M8.1'in `group_by_department`/`rank_top_matches`'i (degistirilmemis)
  DOGRUDAN cagrilir - ham, filtrelenmemis `evaluated_jobs` listesi bu
  fonksiyona verilir.
- "Previously Reported" (Section 16.1/16.3), `EvaluatedJob.
  report_appearances_count` (M1.1, ZATEN mevcut) araciligiyla tespit
  edilir - `ReportRepositoryPort`'un "hesap icin TUM raporlari listele"
  gibi bir metodu YOKTUR (yalnizca tekli ID/run_id sorgulari vardir), bu
  yuzden onceki raporlari toplu sorgulamak mumkun/gerekli degildir.
- `is_bootstrap: bool`, dogrudan cagirana birakilan duz bir parametredir
  (orkestrator, run_logs gecmisinin bos olup olmadigini zaten bilir) -
  bu KONTROL icin ayrica bir RunLogRepositoryPort enjekte edilmez.
- `ai_match_score`i None olan (Scoring Unavailable) bir ilan, FR-11'in
  "gerekli tum alanlari VE gerekce blogunu icerir" kosulunu
  KARSILAYAMAYACAGI icin (gerekce de zorunlu olarak None'dir, bkz.
  EvaluatedJob'un kendi validator'u) render EDILMEZ - M8.1 tarafindan
  zaten gruplanmis/siralanmis olsa bile.

Gercek bir dosya sistemine veya DB'ye HICBIR ZAMAN dokunulmaz -
`JobRepositoryPort`, hand-rolled bir sahte (fake) ile test edilir.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from linkedinbot.domain.evaluated_job import EvaluatedJob, JobStatus, MatchRationaleItem
from linkedinbot.domain.job_posting import JobPosting, WorkplaceType
from linkedinbot.ports.job_repository_port import JobRepositoryPort
from linkedinbot.reporting.compiler import compile_report
from linkedinbot.scoring.company_scoring import CompanyScore

ACCOUNT_ID = uuid4()
RUN_DATE = date(2026, 8, 10)
EVALUATED_AT = datetime(2026, 8, 5, 9, 0, tzinfo=UTC)

GOLDEN_FILE = Path(__file__).parent / "golden" / "expected_report.md"


class _FakeJobRepository(JobRepositoryPort):
    def __init__(self, job_postings: dict[str, JobPosting]):
        self._job_postings = job_postings

    def create(self, job_posting, content_hash):
        raise NotImplementedError

    def get_by_id(self, job_id: str) -> JobPosting | None:
        return self._job_postings.get(job_id)

    def update(self, job_posting, content_hash):
        raise NotImplementedError


def _rationale(company_quality_note: str) -> list[MatchRationaleItem]:
    return [
        MatchRationaleItem(
            component="Department/Role Relevance",
            value="0.9",
            explanation="Matches preferred department.",
        ),
        MatchRationaleItem(
            component="Experience Level Fit", value="Yes", explanation="Matches experience level."
        ),
        MatchRationaleItem(
            component="Location Fit", value="Yes", explanation="Located in Istanbul."
        ),
        MatchRationaleItem(
            component="Company Quality", value="see note", explanation=company_quality_note
        ),
    ]


def _job(**overrides) -> EvaluatedJob:
    data = {
        "account_id": ACCOUNT_ID,
        "job_id": "https://www.linkedin.com/jobs/view/1",
        "company_id": "Acme Corp",
        "ai_match_score": 92.0,
        "match_rationale": _rationale("Prestigious employer."),
        "department_cluster": "Sales & Business Development",
        "status": JobStatus.NEW,
        "first_seen_at": EVALUATED_AT,
        "last_seen_at": EVALUATED_AT,
        "content_hash_at_evaluation": "hash-1",
        "config_version_used": 1,
    }
    data.update(overrides)
    return EvaluatedJob(**data)


def _job_posting(**overrides) -> JobPosting:
    data = {
        "job_id": "https://www.linkedin.com/jobs/view/1",
        "title": "Business Development Executive",
        "company_id": "Acme Corp",
        "location": "Istanbul, Turkey",
        "posted_date": datetime(2026, 8, 5, tzinfo=UTC),
        "description": "Managing key accounts.",
        "application_url": "https://www.linkedin.com/jobs/view/1",
        "collected_at": EVALUATED_AT,
        "workplace_type": WorkplaceType.HYBRID,
        "easy_apply": True,
    }
    data.update(overrides)
    return JobPosting(**data)


def _standard_fixture() -> tuple[list[EvaluatedJob], _FakeJobRepository, dict[str, CompanyScore]]:
    new_job = _job(
        job_id="https://www.linkedin.com/jobs/view/1",
        company_id="Acme Corp",
        status=JobStatus.NEW,
        department_cluster="Sales & Business Development",
        ai_match_score=92.0,
        match_rationale=_rationale("Prestigious employer (Company Quality Score: 85)."),
    )
    updated_job = _job(
        job_id="https://www.linkedin.com/jobs/view/2",
        company_id="Beta Ltd",
        status=JobStatus.UPDATED,
        department_cluster="Marketing",
        ai_match_score=75.0,
        match_rationale=_rationale("Company quality could not be rated."),
    )
    seen_job = _job(
        job_id="https://www.linkedin.com/jobs/view/3",
        company_id="Acme Corp",
        status=JobStatus.SEEN,
        department_cluster="Sales & Business Development",
        ai_match_score=88.0,
        report_appearances_count=2,
        match_rationale=_rationale("Prestigious employer (Company Quality Score: 85)."),
    )
    closed_job = _job(
        job_id="https://www.linkedin.com/jobs/view/4",
        company_id="Acme Corp",
        status=JobStatus.CLOSED,
        department_cluster="Sales & Business Development",
        ai_match_score=99.0,
    )

    job_postings = {
        "https://www.linkedin.com/jobs/view/1": _job_posting(
            job_id="https://www.linkedin.com/jobs/view/1",
            title="Business Development Executive",
            company_id="Acme Corp",
            application_url="https://www.linkedin.com/jobs/view/1",
            workplace_type=WorkplaceType.HYBRID,
            easy_apply=True,
        ),
        "https://www.linkedin.com/jobs/view/2": _job_posting(
            job_id="https://www.linkedin.com/jobs/view/2",
            title="Digital Marketing Specialist",
            company_id="Beta Ltd",
            application_url="https://www.linkedin.com/jobs/view/2",
            workplace_type=WorkplaceType.ON_SITE,
            easy_apply=False,
        ),
        "https://www.linkedin.com/jobs/view/3": _job_posting(
            job_id="https://www.linkedin.com/jobs/view/3",
            title="Sales Executive",
            company_id="Acme Corp",
            application_url="https://www.linkedin.com/jobs/view/3",
            workplace_type=WorkplaceType.REMOTE,
            easy_apply=None,
        ),
    }
    company_scores = {
        "Acme Corp": CompanyScore(
            company_id="Acme Corp",
            weight_profile_id=None,
            rubric_version=1,
            score_total=85.0,
            score_breakdown={},
            evaluated_at=EVALUATED_AT,
        ),
        "Beta Ltd": CompanyScore(
            company_id="Beta Ltd",
            weight_profile_id=None,
            rubric_version=1,
            score_total=None,
            score_breakdown={},
            evaluated_at=EVALUATED_AT,
        ),
    }

    return (
        [new_job, updated_job, seen_job, closed_job],
        _FakeJobRepository(job_postings),
        company_scores,
    )


def test_compiled_report_matches_the_golden_file():
    evaluated_jobs, job_repository, company_scores_by_id = _standard_fixture()

    report = compile_report(
        evaluated_jobs,
        job_repository,
        company_scores_by_id,
        top_n=10,
        run_date=RUN_DATE,
        is_bootstrap=False,
    )

    assert report == GOLDEN_FILE.read_text(encoding="utf-8")


def test_bootstrap_branch_is_triggered_with_an_empty_history():
    evaluated_jobs, job_repository, company_scores_by_id = _standard_fixture()

    report = compile_report(
        evaluated_jobs,
        job_repository,
        company_scores_by_id,
        top_n=10,
        run_date=RUN_DATE,
        is_bootstrap=True,
    )

    assert "Bootstrap" in report or "Initial Scan" in report
    assert "Total new postings" not in report


def test_closed_job_never_appears_in_top_matches_or_department_sections():
    evaluated_jobs, job_repository, company_scores_by_id = _standard_fixture()

    report = compile_report(
        evaluated_jobs,
        job_repository,
        company_scores_by_id,
        top_n=10,
        run_date=RUN_DATE,
        is_bootstrap=False,
    )

    # closed_job'un basligi hicbir yerde GEREKMEZ ama ayni sirketten (Acme
    # Corp) baska ilanlar da var; en guvenilir kontrol job_id/application
    # linki uzerinden yapilir.
    assert "view/4" not in report


def test_previously_reported_job_uses_a_trailing_note_not_a_bracket_tag():
    # Self-review bulgusu: PRD Section 16.1 bu ilanlarin "acikca
    # 'Previously Reported' olarak isaretlenerek" gosterilmesini ister,
    # ama Section 16.3'un etiketleme tablosu AYNI durumu "Etiketsiz"
    # (Untagged) olarak tanimlar. Kullaniciya soruldu, ACIKCA "trailing
    # note, bracket YOK" cozumu secildi - [NEW]/[UPDATED] ile AYNI
    # onek-parantez kuralı kullanilmaz (16.3), ama "Previously Reported"
    # sozcukleri basligin SONUNA bir not olarak eklenir (16.1).
    evaluated_jobs, job_repository, company_scores_by_id = _standard_fixture()

    report = compile_report(
        evaluated_jobs,
        job_repository,
        company_scores_by_id,
        top_n=10,
        run_date=RUN_DATE,
        is_bootstrap=False,
    )

    assert "Sales Executive — Acme Corp (Previously Reported)" in report
    assert "[Previously Reported]" not in report


def test_top_matches_are_limited_by_top_n():
    evaluated_jobs, job_repository, company_scores_by_id = _standard_fixture()

    report = compile_report(
        evaluated_jobs,
        job_repository,
        company_scores_by_id,
        top_n=1,
        run_date=RUN_DATE,
        is_bootstrap=False,
    )

    top_matches_section = report.split("## Top Matches")[1].split("##")[0]
    assert "Business Development Executive" in top_matches_section
    assert "Sales Executive" not in top_matches_section
    assert "Digital Marketing Specialist" not in top_matches_section


def test_seen_job_without_prior_report_appearances_is_not_labeled_previously_reported():
    # Kenar durum: SEEN ama daha once HICBIR raporda gorunmemis (orn.
    # esik/Top-N degisikligi nedeniyle YENI uygun hale gelmis) bir ilan,
    # "Previously Reported" olarak ETIKETLENMEMELIDIR (bu, GERCEK OLMAYAN
    # bir iddia olurdu).
    job = _job(
        job_id="https://www.linkedin.com/jobs/view/5",
        status=JobStatus.SEEN,
        report_appearances_count=0,
        ai_match_score=90.0,
    )
    job_repository = _FakeJobRepository(
        {
            "https://www.linkedin.com/jobs/view/5": _job_posting(
                job_id="https://www.linkedin.com/jobs/view/5",
                application_url="https://www.linkedin.com/jobs/view/5",
            )
        }
    )
    company_scores = {
        "Acme Corp": CompanyScore(
            company_id="Acme Corp",
            weight_profile_id=None,
            rubric_version=1,
            score_total=85.0,
            score_breakdown={},
            evaluated_at=EVALUATED_AT,
        )
    }

    report = compile_report(
        [job], job_repository, company_scores, top_n=10, run_date=RUN_DATE, is_bootstrap=False
    )

    assert "Previously Reported" not in report


def test_empty_input_still_produces_a_non_empty_report():
    # EDGE-7: bos/degismemis bir calistirmada bile rapor TAMAMEN
    # bastirilmaz - en azindan bir ozet satiri her zaman uretilir. Bu
    # testin kendisi EDGE-7'nin TAM METNINI DOGRULAMAZ (Roadmap M8.2'nin
    # kendi Tamamlanma Dogrulamasi bunu acikca istemez, yalnizca
    # Bootstrap'i ister) - yalnizca "asla tamamen bos/bastirilan bir
    # cikti degil" garantisinin dogal olarak saglandigini gosterir.
    job_repository = _FakeJobRepository({})

    report = compile_report(
        [], job_repository, {}, top_n=10, run_date=RUN_DATE, is_bootstrap=False
    )

    assert report.strip() != ""
    assert "Total new postings: 0" in report


def test_job_with_unavailable_ai_match_score_is_not_rendered():
    # FR-11: her girdi "gerekli tum alanlari VE gerekce blogunu" icerir -
    # Scoring Unavailable (ai_match_score=None) bir ilan icin gerekce de
    # None'dir (EvaluatedJob'un kendi validatoru), bu yuzden render
    # EDILEMEZ.
    unavailable_job = _job(
        job_id="https://www.linkedin.com/jobs/view/6",
        ai_match_score=None,
        match_rationale=None,
        status=JobStatus.NEW,
    )
    job_repository = _FakeJobRepository(
        {
            "https://www.linkedin.com/jobs/view/6": _job_posting(
                job_id="https://www.linkedin.com/jobs/view/6",
                application_url="https://www.linkedin.com/jobs/view/6",
            )
        }
    )
    company_scores = {
        "Acme Corp": CompanyScore(
            company_id="Acme Corp",
            weight_profile_id=None,
            rubric_version=1,
            score_total=85.0,
            score_breakdown={},
            evaluated_at=EVALUATED_AT,
        )
    }

    report = compile_report(
        [unavailable_job],
        job_repository,
        company_scores,
        top_n=10,
        run_date=RUN_DATE,
        is_bootstrap=False,
    )

    assert "view/6" not in report


def test_summary_count_includes_new_jobs_with_an_unavailable_ai_match_score():
    # Review bulgusu (Major): FR-11/PRD 16.1'in "toplam yeni ilan sayisi"
    # gereksinimi, AI Match Scoring'in mevcut olup olmadigindan
    # BAGIMSIZDIR - Scoring Unavailable (ai_match_score=None) bir NEW
    # ilan hala GERCEKTEN bulunmus bir yeni ilandir ve ozet sayima dahil
    # edilmelidir, Top Matches/departman bolumlerinden kasitli olarak
    # dislanmasi bundan ayri bir konudur.
    scored_job = _job(
        job_id="https://www.linkedin.com/jobs/view/7",
        status=JobStatus.NEW,
        ai_match_score=90.0,
    )
    unavailable_job = _job(
        job_id="https://www.linkedin.com/jobs/view/8",
        ai_match_score=None,
        match_rationale=None,
        status=JobStatus.NEW,
    )
    job_repository = _FakeJobRepository(
        {
            "https://www.linkedin.com/jobs/view/7": _job_posting(
                job_id="https://www.linkedin.com/jobs/view/7",
                application_url="https://www.linkedin.com/jobs/view/7",
            ),
            "https://www.linkedin.com/jobs/view/8": _job_posting(
                job_id="https://www.linkedin.com/jobs/view/8",
                application_url="https://www.linkedin.com/jobs/view/8",
            ),
        }
    )
    company_scores = {
        "Acme Corp": CompanyScore(
            company_id="Acme Corp",
            weight_profile_id=None,
            rubric_version=1,
            score_total=85.0,
            score_breakdown={},
            evaluated_at=EVALUATED_AT,
        )
    }

    report = compile_report(
        [scored_job, unavailable_job],
        job_repository,
        company_scores,
        top_n=10,
        run_date=RUN_DATE,
        is_bootstrap=False,
    )

    assert "Total new postings: 2" in report
    # Sayima dahil olmasi, render edilmesi gerektigi anlamina gelmez -
    # Scoring Unavailable ilan hala Top Matches/departman bolumlerinde
    # GORUNMEZ (gecerli bir gerekce blogu olmadigi icin).
    assert "view/8" not in report
