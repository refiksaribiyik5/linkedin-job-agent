"""Run Orchestrator - PRD Section 10, TDD Section 8/17/20 (Roadmap M9.3).

**Tek is:** Collection -> Normalization -> History -> Filtering ->
Company Scoring -> AI Matching -> Ranking/Reporting -> State Update ->
Logging'i TEK bir fonksiyon cagrisinda birlestirmek (Roadmap M9.3'un
kendi Amac metni). Bu modul SADECE ORKESTRASYONDUR - hicbir asamanin
KENDI is mantigini yeniden uygulamaz; her asamanin ZATEN onaylanmis,
degistirilmemis fonksiyonunu/sinifini SIRAYLA cagirir, ARALARINDA veri
sekillendirir (bir asamanin ciktisini bir sonrakinin girdisine cevirir)
ve transaction sinirlarini/hata yayilimini yonetir.

**"Eager cache, atomic final state" (TDD Section 17):** `job_postings`,
`companies`, `company_scores` yazmalari HEMEN commit edilir (pipeline
ilerledikce) - bir kesinti durumunda "fazladan" yazilmis olmalari
zararsizdir ve bir sonraki calistirmanin ayni LinkedIn/LLM cagrilarini
TEKRARLAMASINI onler. `evaluated_jobs`/`reports`/(Success/Partial)
`run_logs` TEK bir final transaction'da birlikte commit edilir (State
Update, PRD adim 11).

**Hata sinifi ayrimi (TDD Section 20, M9.4 "Hata Siniflandirma + Retry"
ile GUNCELLENDI):** `TransientError`/`PermanentError` taksonomisi
(errors.py) ve backoff/devre-kesici-lite mekanizmasi (retry.py) artik
insa edildi - LinkedIn cagri noktasinda (`collection/collector.py`)
KULLANILIR. Bu modulun KENDI sorumlulugu degismedi: pipeline'dan
(Session Validation'dan State Update'e kadar) yukselen HERHANGI bir
istisnayi (retry tukenmis bir `TransientError` DAHIL) tek, merkezi bir
noktada yakalayip Run'in nihai durumunu (Success/Partial/Failed)
belirler (TDD Section 20'nin "yalnizca Run Orchestrator bu istisnalardan
Run'in nihai durumunu belirler" ilkesi). "Partial", `TransientError`
YAKALANARAK degil, `collection_result.is_complete`'in (Collection Service
NORMAL DONUS DEGERI - bkz. `collection/collector.py::CollectionResult`
modul dokumani, "unified completeness" tasarimi, bagimsiz review sonrasi)
OKUNMASIYLA belirlenir - pipeline devre kesici/sinir/kismi-sorgu-basarisizligi
sonrasi KESILMEZ, elde edilen kismi veriyle NORMAL sekilde devam eder.
`is_complete=False`'un UC bagimsiz sebebi olabilir (devre kesici, FR-21
sinirina ulasilmasi, veya esik-alti bir sorgunun tum denemelerini
tuketmesi) - bu modul bunlarin HICBIRINI ayri ayri sormaz, TEK bir
`is_complete` okumasiyla Run'in nihai durumunu belirler. LLM cagri
noktasindaki (`adapters/llm/anthropic_adapter.py`) retry entegrasyonu
ayri, sonraki bir adimdir.

**Basarisiz bir calistirmada run_logs (FR-15 vs EDGE-14 uzlasimi, M9.2
gorusme turunde onaylanan tasarim):** PRD'nin 12 adimli pipeline'i
Logging'i (adim 12) State Update'ten (adim 11) SONRA, AYRI bir adim
olarak listeler ve acikca "hata/basarisizlik durumu en az yerel olarak
gorunur bir sinyalle isaretlenir" der (FR-1). Bu, TDD Section 17'nin
"run_logs TEK final transaction'in parcasidir" ifadesinin yalnizca
BASARILI/PARCALI yolu tarif ettigini, EDGE-14'un (gercek surec cokmesi)
ise TAMAMEN farkli, kurtarilamaz bir senaryo oldugunu dogrular. Bu
yuzden: pipeline ortasinda YAKALANAN bir hata, batch transaction'i geri
alir (evaluated_jobs/reports/olacak-olan-Success-run_logs hic commit
edilmez) VE AYRI, kucuk bir commit'le TEK bir Failed run_logs satiri
yazar (FR-15'in "sessiz hata olusmaz" gereksinimini karsilar). Roadmap
M9.3'un kendi "evaluated_jobs/reports/run_logs'un degismedigi"
tamamlanma kriteri, bu ayri Failed-satiri EKLEMESI HARIC, ONCEDEN VAR
OLAN satirlarin bozulmadigi/degismedigi anlamina gelir - EDGE-14'un
kendi SOZ KONUSU ETTIGI senaryo (gercek bir surec cokmesi, hicbir
Python istisnasinin yakalanamayacagi) bu modulun kapsami DISINDADIR
(bu modul yalnizca YAKALANABILIR Python istisnalarini ele alir).

**RunLock ne zaman alinir/birakilir:** `RunLock.acquire()` calistirmanin
EN BASINDA (Session Validation'dan bile ONCE) cagrilir - basarisiz
olursa (`RunAlreadyInProgressError`) HICBIR ISLEM yapilmaz, HICBIR
run_logs satiri yazilmaz (bu, "hicbir is denenmedi" senaryosudur, FR-15'in
"basarisiz bir calistirma" senaryosundan AYRIDIR - kullaniciya "zaten
calisiyor" mesajini gostermek gelecekteki CLI/Scheduler'in (M9.6/M9.7)
isidir, bkz. TDD'nin manuel-tetikleme akisi metni). `RunLock.release()`
HER durumda (basari, basarisizlik, veya pipeline hatasi) calistirmanin
EN SONUNDA cagrilir.

**Model kademelendirmesi (M9.3 tasarim incelemesinde bulunan Gap C,
kullaniciya acikca sunulup implementasyon-zamani karari olarak
onaylandi):** TDD Section 10'un tablosu 4 cagri turunu 3 SOYUT kademeye
esler ("Hizli/ucuz", "Orta", "Yuksek kaliteli") ama HICBIR YERDE somut
bir model kimligine baglanmaz - `adapters/llm/gateway.py`'nin (M5.3)
kendi onaylanmis dokumani bu kararin "GELECEKTEKI cagirana" (bu modul)
birakildigini ACIKCA belirtir. Asagidaki sabitler bu kademelemeyi somut
model kimliklerine baglar.

**`weight_profile_id`/`rubric_version` (M9.3 tasarim incelemesinde
bulunan Gap A, implementasyon-zamani karari):** PRD Section 12.4'un
cok-kullanicili onbellekleme kurali (sistem varsayilani vs. hesaba ozel
agirlik) V1'in tek-hesapli kapsaminda anlamli bir ayrim degildir - hicbir
config alani "bu agirliklar sistem varsayilanindan farkli mi" sorusunu
cevaplamaz (bkz. M9.3 tasarim incelemesi, Gap A). Bu yuzden V1 icin
`weight_profile_id` HER ZAMAN `None` (sistem varsayilani) ve
`rubric_version` sabit `1`'dir - bu, gelecekteki bir cok-kullanicili
fazda geriye donuk uyumludur (mevcut `None`-anahtarli kayitlar
degismeden kalir, yeni hesaba-ozel kayitlar farkli bir
`weight_profile_id` ile eklenir).

**`JobStatus.EXCLUDED` NE ZAMAN atanir (M9.3 implementasyonu sirasinda
cozumlenen, PRD/TDD metninden dogrudan turetilen tasarim karari):**
FR-19'un kendi kabul kriteri ACIKCA "tum filtrelerden GECSE ve yuksek
skor ALSA dahi" der - yani Blacklist disiplini, DIGER filtrelerin
(Location/Experience/Department) basarisiz olmasindan KAVRAMSAL olarak
BAGIMSIZDIR; `EXCLUDED`, TDD Section 17'nin durum makinesi grafiginde
(New/Seen/Updated/Closed) YER ALMAZ (diff_engine.py'nin kendi
dokumaninda zaten dogrulanmis bir gozlem) - bu, EXCLUDED'in GENEL bir
"herhangi bir filtre basarisiz oldu" sonucu DEGIL, SPESIFIK olarak
Blacklist'e (FR-19) baglanan, kalici/yapiskan bir durum oldugunu
gosterir. Location/Experience/Department'ten (Blacklist DEGIL)
reddedilen bir ilan, `diff_job_postings()`'in ZATEN atadigi durumu
(New/Updated) KORUR, `ai_match_score=None` ile - `reporting/compiler.py`
(M8.2, degistirilmemis) BOYLE bir ilani zaten otomatik olarak
raporlardan gizler (aynen "Scoring Unavailable" durumuyla AYNI kod
yolu), bu yuzden AYRI bir durum GEREKMEZ.

**Yapilandirilmis loglama (Roadmap M9.5, TDD Section 19):** `logging.StructuredLogger`
bir Port DEGILDIR (TDD Section 7'nin "yatay kesen katman"i - herhangi bir
modulun bagimli olabilecegi capraz-kesen bir servis); bu modul, `run_logs`
DB tablosunun (kalici, sorgulanabilir gozlemlenebilirlik sozlesmesi,
degismedi) YANINDA, gecici/dosya-tabanli JSON log satirlari uretir. INFO
cagrilari `_run_pipeline()`'in dogal asama sinirlarinda (Session Validation,
Collection, History, Evaluation, Report Compilation, State Update) yer
alir; TEK bir WARNING cagrisi EDGE-9 (kismi sonuc, `is_complete=False`)
icindir; TEK bir ERROR cagrisi `run()`'in merkezi hata yakalama noktasinda,
`error_detail`in AYNI `exc` degerinden AYNI kod noktasinda dolduruldugu
yerdedir - TDD Section 19'un "her ERROR run_logs.error_detail'i doldurmak
ZORUNDADIR" kuralinin yapisal garantisi budur (ayri bir dogrulama testiyle
denetlenir). Hesabin hic var olmadigi (IntegrityError re-raise) uc durumda
HICBIR ERROR logu yazilmaz - o yolda zaten hicbir `run_logs` satiri
YAZILAMAZ (yukaridaki not), bu yuzden eslesecek bir `error_detail` yoktur.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from linkedinbot.collection.collector import collect_raw_job_cards, extract_records
from linkedinbot.config.loader import load_account_context
from linkedinbot.domain.company_profile import CompanyProfile
from linkedinbot.domain.evaluated_job import EvaluatedJob, JobStatus
from linkedinbot.domain.report import Report
from linkedinbot.domain.run_log import RunLog, RunStatus, TriggerType
from linkedinbot.filtering.pipeline import PipelineResult, run_filtering_pipeline
from linkedinbot.history.diff_engine import PreviousEvaluation, diff_job_postings
from linkedinbot.normalization.normalizer import normalize_record
from linkedinbot.ranking.ranker import group_by_department, rank_top_matches
from linkedinbot.reporting.compiler import compile_report
from linkedinbot.run.run_lock import RunLock
from linkedinbot.scoring.ai_matching import compute_is_borderline, score_ai_match
from linkedinbot.scoring.company_scoring import CompanyScore, score_company

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from linkedinbot.adapters.llm.gateway import LLMGateway
    from linkedinbot.domain.account_context import AccountContext
    from linkedinbot.domain.job_posting import JobPosting
    from linkedinbot.logging.structured_logger import StructuredLogger
    from linkedinbot.ports.company_repository_port import CompanyRepositoryPort
    from linkedinbot.ports.company_score_repository_port import CompanyScoreRepositoryPort
    from linkedinbot.ports.evaluated_job_repository_port import EvaluatedJobRepositoryPort
    from linkedinbot.ports.job_repository_port import JobRepositoryPort
    from linkedinbot.ports.linkedin_port import LinkedInPort
    from linkedinbot.ports.report_repository_port import ReportRepositoryPort
    from linkedinbot.ports.report_store_port import ReportStorePort
    from linkedinbot.ports.run_log_repository_port import RunLogRepositoryPort

# Gap C (model kademelendirmesi) - TDD Section 10 tablosunun 3 soyut
# kademesinin somut model kimliklerine baglanmasi.
FAST_MODEL = "claude-haiku-4-5-20251001"
MID_MODEL = "claude-sonnet-5"
HIGH_QUALITY_MODEL = "claude-opus-5"

# Gap A (weight_profile_id/rubric_version) - V1 tek-hesapli kapsaminda
# "sistem varsayilani" HER ZAMAN gecerlidir.
_RUBRIC_VERSION = 1

# TDD Section 22 "İstekler arası... Sabit gecikme + jitter" - M3.5'in
# kendi onaylanmis dokumaninin acikca "sabit bir varsayilan" olarak
# yetkilendirdigi bir karar (bkz. collection/collector.py modul dokumani).
_COLLECTION_DELAY_SECONDS = 2.0
_COLLECTION_JITTER_SECONDS = 1.0


class RunAlreadyInProgressError(Exception):
    """RunLock zaten baska bir sahip tarafindan tutuluyorken acquire()
    basarisiz oldugunda firlatilir. HICBIR is yapilmamistir - hicbir
    run_logs satiri yazilmaz (bkz. modul dokumani). Kullaniciya
    "zaten calisiyor" mesajini gostermek gelecekteki CLI/Scheduler'in
    (M9.6/M9.7) sorumlulugundadir.
    """


@dataclass
class OrchestratorDependencies:
    """Orchestrator'in ihtiyac duydugu TUM altyapi bagimliliklari - hepsi
    ZATEN onaylanmis, degistirilmemis Port'lar/adaptorler/sinif
    orneklerine referanstir. Bu modul HICBIRINI somutlastirmaz (kendi
    concrete implementasyonunu secmez) - cagiran (gelecekteki M9.6/M9.7)
    hangi adaptorlerin kullanilacagina karar verir.

    `structured_logger` (Roadmap M9.5, TDD Section 19): `logging.StructuredLogger`
    bir Port DEGILDIR (TDD Section 7'nin "yatay kesen katman" - herhangi
    bir modulun bagimli olabilecegi capraz-kesen bir servis, ozel bir
    soyutlama katmani gerektirmez); yine de digerleriyle AYNI enjeksiyon
    deseniyle burada tasinir - orchestrator kendi StructuredLogger
    ornegini somutlastirmaz, cagiran (gelecekteki M9.6/M9.7) hangi
    dosya yolu/seviye ile kurulacagina karar verir.
    """

    session: Session
    linkedin_port: LinkedInPort
    llm_gateway: LLMGateway
    report_store: ReportStorePort
    job_repository: JobRepositoryPort
    company_repository: CompanyRepositoryPort
    company_score_repository: CompanyScoreRepositoryPort
    evaluated_job_repository: EvaluatedJobRepositoryPort
    report_repository: ReportRepositoryPort
    run_log_repository: RunLogRepositoryPort
    structured_logger: StructuredLogger


def _company_context(company: CompanyProfile) -> str:
    """CompanyProfile'in (M1.1, degistirilmemis) mevcut alanlarindan kisa
    bir metin blogu olusturur - `score_company()`'nin `company_context: str`
    parametresi icin. V1'de hicbir pipeline asamasi industry/employee_
    count_range/founded_year'i doldurmaz (CompanyProfile bunlari HER ZAMAN
    Optional tasir, PRD Section 12.3'un "yeterli veri olmayabilir"
    kabulune uygun); bu durumda `score_company()`'nin ZATEN onaylanmis
    prompt sablonu "insufficient information" olarak dogru sekilde ele
    alir - bu modul UYDURMA bir baglam URETMEZ.
    """
    lines = []
    if company.industry:
        lines.append(f"Industry: {company.industry}")
    if company.employee_count_range:
        lines.append(f"Employee count: {company.employee_count_range}")
    if company.founded_year:
        lines.append(f"Founded: {company.founded_year}")
    if not lines:
        return "No additional information available."
    return "\n".join(lines)


def _get_or_create_company(
    company_repository: CompanyRepositoryPort, company_id: str
) -> CompanyProfile:
    existing = company_repository.get_by_id(company_id)
    if existing is not None:
        return existing
    return company_repository.create(CompanyProfile(company_id=company_id, name=company_id))


def _get_or_score_company(
    *,
    company_id: str,
    dependencies: OrchestratorDependencies,
    weights,
    reevaluation_window_days: int,
    now: datetime,
    company_scores_this_run: dict[str, CompanyScore],
) -> CompanyScore:
    """Sirket skorunu, once BU calistirma icindeki bellek-ici onbellekten,
    sonra CompanyScoreRepository'den (M9.2) tazelik penceresi icindeyse,
    ancak HICBIRINDE bulunamazsa `score_company()` (M7.1, degistirilmemis)
    cagirarak elde eder. `score_company()`'nin KENDI `cached_scores`
    parametresi BILEREK bos birakilir - tazelik kontrolu BURADA (cagiran
    tarafinda) zaten yapildigi icin (Roadmap M9.2'nin kendi Amac metni:
    "tazelik penceresi degerlendirmesi ... Orchestrator'in sorumlulugunda
    kalir").
    """
    if company_id in company_scores_this_run:
        return company_scores_this_run[company_id]

    existing = dependencies.company_score_repository.get_by_key(
        company_id, None, _RUBRIC_VERSION
    )
    if existing is not None:
        age = now - existing.evaluated_at
        if age <= timedelta(days=reevaluation_window_days):
            company_scores_this_run[company_id] = existing
            return existing

    company = _get_or_create_company(dependencies.company_repository, company_id)
    computed = score_company(
        company_id=company_id,
        company_context=_company_context(company),
        weights=weights,
        weight_profile_id=None,
        rubric_version=_RUBRIC_VERSION,
        cached_scores={},
        llm_gateway=dependencies.llm_gateway,
        model=MID_MODEL,
        evaluated_at=now,
    )
    if existing is None:
        persisted = dependencies.company_score_repository.create(computed)
    else:
        persisted = dependencies.company_score_repository.update(computed)
    company_scores_this_run[company_id] = persisted
    return persisted


def _blacklist_rejected(pipeline_result: PipelineResult) -> bool:
    blacklist_result = pipeline_result.filter_result_detail.get("blacklist")
    return blacklist_result is not None and not blacklist_result.passed


def _reused_seen_job(previous: EvaluatedJob, now: datetime) -> EvaluatedJob:
    """SEEN olarak siniflandirilan (icerigi degismemis) bir ilan icin,
    FR-18'in is-seviyesi onbellekleme gereksiniminin dogal sonucu:
    filtreleme/skorlama YENIDEN CALISTIRILMAZ (ayni girdi + ayni config
    ayni sonucu uretecegi icin), var olan EvaluatedJob AYNEN yeniden
    kullanilir.

    `status` ACIKCA `JobStatus.SEEN`'e ayarlanir (self-review bulgusu,
    gercek defect): `previous` nesnesinin KENDI `status` alani ONCEKI
    calistirmadan kalma (orn. hala `NEW`) olabilir - `diff_job_postings()`
    (M4.2) BU tarama icin zaten `SEEN` karari VERMISTIR (cagiran bu
    fonksiyonu SADECE `status == JobStatus.SEEN` dalinda cagirir), ama
    `previous`'un KENDI alanini kopyalamak bu YENI karari yansitmaz -
    `model_copy()` `status`'u da acikca guncellemezse, ilan SONSUZA
    KADAR ilk atandigi durumda (orn. `NEW`) "takili" kalir ve hicbir
    zaman gercekte SEEN olarak isaretlenmez.
    """
    return previous.model_copy(update={"last_seen_at": now, "status": JobStatus.SEEN})


def _evaluate_new_or_updated_job(
    *,
    job_posting: JobPosting,
    status: JobStatus,
    content_hash: str,
    dependencies: OrchestratorDependencies,
    account_context,
    now: datetime,
    company_scores_this_run: dict[str, CompanyScore],
) -> tuple[EvaluatedJob, bool]:
    """Doner: `(EvaluatedJob, passed_filtering)` - `passed_filtering`,
    `run_logs.jobs_filtered`'in (PRD 15.6, "toplanan/filtrelenen/yeni/
    kapanan ilan sayilari" funnel'i) BU ilanin filtreleme asamasini
    GECIP GECMEDIGINI cagirana bildirmesi icindir; `EvaluatedJob`'un
    kendisi bu bilgiyi ayri, sorgulanabilir bir alan olarak TASIMAZ
    (yalnizca dolayli olarak status/ai_match_score'dan cikarilabilir).
    """
    config_profile = account_context.config_profile
    thresholds = config_profile.thresholds

    pipeline_results = run_filtering_pipeline(
        [job_posting],
        account_context.user_profile.preferences,
        config_profile.target_criteria.locations,
        config_profile.target_criteria.experience_levels,
        config_profile.target_criteria.departments,
        thresholds.department_confidence,
        thresholds.department_confidence_tolerance,
        dependencies.llm_gateway,
        FAST_MODEL,
    )
    _, pipeline_result = pipeline_results[0]

    if not pipeline_result.passed:
        final_status = JobStatus.EXCLUDED if _blacklist_rejected(pipeline_result) else status
        return (
            EvaluatedJob(
                account_id=account_context.account_id,
                job_id=job_posting.job_id,
                company_id=job_posting.company_id,
                department_cluster=None,
                filter_result_detail=pipeline_result.filter_result_detail,
                status=final_status,
                is_borderline=False,
                first_seen_at=now,
                last_seen_at=now,
                content_hash_at_evaluation=content_hash,
                config_version_used=account_context.config_version,
            ),
            False,
        )

    company_score = _get_or_score_company(
        company_id=job_posting.company_id,
        dependencies=dependencies,
        weights=config_profile.weights_company_quality,
        reevaluation_window_days=thresholds.company_score_reevaluation_window_days,
        now=now,
        company_scores_this_run=company_scores_this_run,
    )

    department_result = pipeline_result.filter_result_detail["department"]
    experience_result = pipeline_result.filter_result_detail["experience"]
    location_result = pipeline_result.filter_result_detail["location"]

    ai_result = score_ai_match(
        job_id=job_posting.job_id,
        account_id=account_context.account_id,
        config_version=account_context.config_version,
        job_title=job_posting.title,
        job_description=job_posting.description,
        career_goals=account_context.user_profile.career_goals,
        department_relevance_confidence=department_result.confidence or 0.0,
        experience_level_fit=experience_result.passed,
        location_fit=location_result.passed,
        company_score=company_score,
        weights=config_profile.weights_ai_match,
        cached_results={},
        llm_gateway=dependencies.llm_gateway,
        model=HIGH_QUALITY_MODEL,
        evaluated_at=now,
    )

    is_borderline = compute_is_borderline(
        ai_result.ai_match_score,
        thresholds.ai_match_score,
        thresholds.borderline_band_width,
        filtering_is_borderline=pipeline_result.is_borderline,
    )

    return (
        EvaluatedJob(
            account_id=account_context.account_id,
            job_id=job_posting.job_id,
            company_id=job_posting.company_id,
            ai_match_score=ai_result.ai_match_score,
            match_rationale=ai_result.match_rationale,
            department_cluster=department_result.matched_cluster,
            filter_result_detail=pipeline_result.filter_result_detail,
            status=status,
            is_borderline=is_borderline,
            first_seen_at=now,
            last_seen_at=now,
            content_hash_at_evaluation=content_hash,
            config_version_used=account_context.config_version,
        ),
        True,
    )


def _persist_evaluated_job(
    evaluated_job_repository: EvaluatedJobRepositoryPort,
    evaluated_job: EvaluatedJob,
    *,
    is_new: bool,
) -> EvaluatedJob:
    if is_new:
        return evaluated_job_repository.create(evaluated_job)
    return evaluated_job_repository.update(evaluated_job)


def _run_pipeline(
    *,
    account_id: UUID,
    account_context: AccountContext,
    dependencies: OrchestratorDependencies,
    run_id: UUID,
    trigger_type: TriggerType,
    now: datetime,
    is_bootstrap: bool,
) -> RunLog:
    dependencies.linkedin_port.validate(account_id)
    dependencies.structured_logger.info(
        account_id=account_id,
        run_id=run_id,
        stage="Session Validation",
        message="Oturum dogrulandi.",
    )

    config_profile = account_context.config_profile

    thresholds = config_profile.thresholds
    collection_result = collect_raw_job_cards(
        dependencies.linkedin_port,
        account_id,
        config_profile.target_criteria,
        config_profile.collection_limits.max_jobs_per_run,
        _COLLECTION_DELAY_SECONDS,
        _COLLECTION_JITTER_SECONDS,
        thresholds.linkedin_retry_attempts,
        thresholds.retry_base_delay_ms,
        thresholds.retry_max_delay_ms,
        thresholds.linkedin_consecutive_failure_threshold,
    )
    raw_records = extract_records(collection_result.raw_cards)
    jobs_collected = len(raw_records)
    dependencies.structured_logger.info(
        account_id=account_id,
        run_id=run_id,
        stage="Collection",
        message=f"{jobs_collected} ham ilan toplandi.",
        extra={
            "jobs_collected": jobs_collected,
            "collection_capped": collection_result.collection_capped,
        },
    )
    if not collection_result.is_complete:
        # EDGE-9 (kismi sonuc) - TDD Section 19'un WARNING orneginin
        # BIREBIR karsiligi: kurtarilabilir bir anomali, Run'i durdurmaz.
        dependencies.structured_logger.warning(
            account_id=account_id,
            run_id=run_id,
            stage="Collection",
            message=collection_result.partial_reason or "Toplama tam degil.",
        )

    current_scan = [normalize_record(record, now) for record in raw_records]
    content_hash_by_job_id = {
        job_posting.job_id: content_hash for job_posting, content_hash in current_scan
    }

    previous_by_job_id = {
        evaluated.job_id: evaluated
        for evaluated in dependencies.evaluated_job_repository.list_by_account(account_id)
    }
    previous_evaluations = {
        job_id: PreviousEvaluation(
            status=evaluated.status, content_hash=evaluated.content_hash_at_evaluation
        )
        for job_id, evaluated in previous_by_job_id.items()
    }

    diff_results, newly_closed_job_ids = diff_job_postings(current_scan, previous_evaluations)
    dependencies.structured_logger.info(
        account_id=account_id,
        run_id=run_id,
        stage="History",
        message=f"{len(diff_results)} ilan gecmisle karsilastirildi.",
        extra={
            "diffed": len(diff_results),
            "candidate_closures": len(newly_closed_job_ids),
        },
    )

    # Eager write: companies, sonra job_postings (TDD Section 17 - hemen
    # yazilabilir veri). Sira KASITLIDIR: `job_postings.company_id`,
    # `companies.company_id`'ye bir FOREIGN KEY tasir (bkz. db/models.py
    # JobPostingOrm) - bir ilan satirini, henuz var olmayan bir sirkete
    # referansla yazmak bir butunluk ihlalidir; bu yuzden HER benzersiz
    # sirket, o sirkete ait herhangi bir ilan yazilmadan ONCE
    # var-olustur edilir.
    for company_id in {job_posting.company_id for job_posting, _status in diff_results}:
        _get_or_create_company(dependencies.company_repository, company_id)

    for job_posting, _status in diff_results:
        content_hash = content_hash_by_job_id[job_posting.job_id]
        if dependencies.job_repository.get_by_id(job_posting.job_id) is None:
            dependencies.job_repository.create(job_posting, content_hash)
        else:
            dependencies.job_repository.update(job_posting, content_hash)
    dependencies.session.commit()

    evaluated_jobs: list[EvaluatedJob] = []
    company_scores_this_run: dict[str, CompanyScore] = {}
    jobs_filtered = 0

    for job_posting, status in diff_results:
        if status == JobStatus.SEEN:
            evaluated_jobs.append(_reused_seen_job(previous_by_job_id[job_posting.job_id], now))
            continue

        content_hash = content_hash_by_job_id[job_posting.job_id]
        evaluated_job, passed_filtering = _evaluate_new_or_updated_job(
            job_posting=job_posting,
            status=status,
            content_hash=content_hash,
            dependencies=dependencies,
            account_context=account_context,
            now=now,
            company_scores_this_run=company_scores_this_run,
        )
        if passed_filtering:
            jobs_filtered += 1
        evaluated_jobs.append(evaluated_job)

    dependencies.session.commit()  # eager: companies/company_scores (Section 17)
    dependencies.structured_logger.info(
        account_id=account_id,
        run_id=run_id,
        stage="Evaluation",
        message=f"{jobs_filtered} ilan filtreleri gecti.",
        extra={"jobs_filtered": jobs_filtered},
    )

    # Kapanan ilanlar: onceki EvaluatedJob'un status'u Closed'e cevrilir.
    #
    # M9.4 duzeltmesi (self-review + bagimsiz review, uc AYRI gercek defect
    # bulundu ve "unified completeness" tasarimiyla TEK bir koruma altinda
    # birlestirildi): `collection_result.is_complete=False` ise (devre
    # kesici tetiklendi, FR-21 hacim sinirina ulasildi, VEYA bir sorgu
    # devre kesici esigine ulasmadan tum yeniden deneme denemelerini
    # tuketti) bu adim TAMAMEN ATLANIR - ucu de AYNI kokten (eksik/kesintiye
    # ugramis bir tarama) kaynaklanan tetikleyicilerdir. FR-21'in kendi
    # kabul kriteri, sinira ulasilan bir calistirmayi acikca "kesildi"
    # (toplama KESILDI) olarak tanimlar. `diff_job_postings()`'in (M4.2,
    # degistirilmemis) "current_scan'de gorunmeyen HER onceki ilan
    # kapanmistir" varsayimi, taranmayan/basarisiz olan HERHANGI bir
    # sorgu/sayfa oldugunda GECERSIZDIR: o sorgunun/sayfanin bulacagi
    # ilanlarin GERCEKTEN kapandigi anlamina GELMEZ, yalnizca BU
    # calistirmada yeniden dogrulanamadiklari anlamina gelir. FR-10
    # "Closed Job Detection," yalnizca GERCEKTEN kapali ilanlar icindir;
    # bu koruma olmadan boyle bir calistirma, hesabin tarama sirasinda
    # henuz ulasilmamis/dogrulanamamis TUM acik ilanlarini yanlislikla
    # Closed isaretleyip raporlardan sessizce dusururdu. Bu ilanlar, bir
    # SONRAKI (tam) taramada normal sekilde yeniden degerlendirilecektir.
    #
    # `scan_is_incomplete`, asagida `jobs_closed` sayimi icin de AYNEN
    # kullanilir - iki yerin birbirinden SAPMASINI (orn. `jobs_closed`'in
    # atlanan bir adimi HALA sayiyor gibi gorunmesini) onlemek icin TEK
    # bir bayrakta birlestirilir.
    scan_is_incomplete = not collection_result.is_complete
    if not scan_is_incomplete:
        for job_id in newly_closed_job_ids:
            previous = previous_by_job_id[job_id]
            evaluated_jobs.append(previous.model_copy(update={"status": JobStatus.CLOSED}))

    top_matches_count = config_profile.report_format_settings.top_matches_count
    top_matches = rank_top_matches(evaluated_jobs, top_matches_count)
    top_match_job_ids = [job.job_id for job in top_matches]

    # `compile_report()` (M8.2, degistirilmemis) departman bolumlerini
    # render ETMEDEN once `ai_match_score is not None` ile AYRICA filtreler
    # (bkz. reporting/compiler.py) - Report.included_job_ids'in GERCEKTEN
    # render edilen ilanlarla eslesmesi icin bu modul de AYNI filtreyi
    # burada tekrarlar (compile_report()'un KENDI ic mantigini
    # degistirmeden, yalnizca onun DAVRANISINI bu ayri hesaplamada
    # yansitarak).
    department_groups = group_by_department(evaluated_jobs)
    rendered_department_job_ids = {
        job.job_id
        for jobs in department_groups.values()
        for job in jobs
        if job.ai_match_score is not None
    }
    included_job_ids = sorted(rendered_department_job_ids | set(top_match_job_ids))

    # Backfill (self-review bulgusu, gercek defect): SEEN ilanlar
    # `_evaluate_new_or_updated_job()`'u hic calistirmaz (`_reused_seen_job()`
    # ile wholesale yeniden kullanilirlar) - bu yuzden sirketleri BU
    # calistirmanin `company_scores_this_run` onbellegine hic eklenmemis
    # olabilir. Ama `rank_top_matches()` (ranking/ranker.py, degistirilmemis)
    # SEEN ilanlari da Top Matches'e uygun sayar (yalnizca departman
    # bolumleri NEW/UPDATED ile sinirlidir, bkz. group_by_department) - bu
    # yuzden onceden raporlanmis, degismemis GUCLU bir ilan SONRAKI bir
    # calistirmada Top Matches'te tekrar gorunebilir. `compile_report()`
    # (M8.2), rapora GIRECEK HER ilan icin bir CompanyScore lookup'ini
    # ZORUNLU kilar (bkz. `_company_quality_score()` - eksik anahtar
    # ValueError firlatir) - bu yuzden raporA GIRECEK (`included_job_ids`)
    # her ilanin sirketi icin, henuz onbellekte yoksa, digerleriyle AYNI
    # tazelik-penceresi farkindaligina sahip `_get_or_score_company()`
    # cagrilir.
    evaluated_jobs_by_id = {job.job_id: job for job in evaluated_jobs}
    for job_id in included_job_ids:
        company_id = evaluated_jobs_by_id[job_id].company_id
        if company_id not in company_scores_this_run:
            _get_or_score_company(
                company_id=company_id,
                dependencies=dependencies,
                weights=config_profile.weights_company_quality,
                reevaluation_window_days=(
                    config_profile.thresholds.company_score_reevaluation_window_days
                ),
                now=now,
                company_scores_this_run=company_scores_this_run,
            )
    dependencies.session.commit()  # eager: backfilled company_scores (Section 17)

    # `jobs_new`, `evaluated_jobs`'un `status == JobStatus.NEW` olan
    # UYELERININ SAYISIDIR (kalicilik katmaninda create-vs-update
    # ayrimindan BAGIMSIZ) - `diff_engine.py`'nin (M4.2) NEW atadigi IKI
    # durum da (hic bilinmeyen bir ilan VEYA yeniden acilan onceden Closed
    # bir ilan, EDGE-5) raporda AYNI sekilde "[NEW]" ile gosterilir (bkz.
    # reporting/compiler.py `_bracket_tag`) - bu yuzden ikisi de PRD 15.6'nin
    # "yeni ilan sayisi" istatistigine ayni sekilde katilir.
    jobs_new = sum(1 for job in evaluated_jobs if job.status == JobStatus.NEW)

    # RunLog, Report'tan ONCE olusturulur/create() edilir (sira KASITLIDIR):
    # `reports.run_id`, `run_logs.run_id`'ye bir FOREIGN KEY tasir (bkz.
    # db/models.py ReportOrm) - butun bu yazmalar HALA AYNI, henuz commit
    # edilmemis transaction icindedir (TDD Section 17 "atomic final state"),
    # bu yuzden bu sadece INSERT sirasidir, ayri bir commit DEGILDIR.
    #
    # Partial (M9.4, "unified completeness" duzeltmesi): `not
    # collection_result.is_complete`, UC bagimsiz sebepten (devre kesici,
    # FR-21 hacim siniri, veya esik-alti bir sorgu basarisizligi)
    # HERHANGI birinin gerceklestigini gosterir - PRD Section 15.7 geregi
    # bu HALA bir rapor ureten, TAM TESEKKULLU bir sonuctur (Failed
    # DEGILDIR); pipeline bu noktaya kadar zaten `collection_result.raw_cards`
    # (ne kadar toplanabildiyse) ile normal sekilde devam etmistir. Tek
    # istisna, yukaridaki "Kapanan ilanlar" adiminin `scan_is_incomplete`
    # iken BILEREK atlanmasidir (yanlis-kapatma korumasi) - bu yuzden
    # `jobs_closed` burada `newly_closed_job_ids`'in HAM uzunlugu DEGIL, o
    # adimda FIILEN Closed isaretlenen sayidir (scan eksikken her zaman 0).
    jobs_closed = 0 if scan_is_incomplete else len(newly_closed_job_ids)
    run_log = RunLog(
        run_id=run_id,
        account_id=account_id,
        trigger_type=trigger_type,
        started_at=now,
        ended_at=now,
        jobs_collected=jobs_collected,
        jobs_filtered=jobs_filtered,
        jobs_new=jobs_new,
        jobs_closed=jobs_closed,
        status=RunStatus.SUCCESS if collection_result.is_complete else RunStatus.PARTIAL,
        partial_reason=(
            None if collection_result.is_complete else collection_result.partial_reason
        ),
        collection_capped=collection_result.collection_capped,
    )
    created_run_log = dependencies.run_log_repository.create(run_log)

    report_content = compile_report(
        evaluated_jobs,
        dependencies.job_repository,
        dict(company_scores_this_run),
        top_matches_count,
        now.date(),
        is_bootstrap,
    )

    report_id = uuid4()
    storage_path = dependencies.report_store.save(account_id, report_id, now, report_content)
    dependencies.report_repository.create(
        Report(
            report_id=report_id,
            account_id=account_id,
            run_id=run_id,
            generated_at=now,
            included_job_ids=included_job_ids,
            top_matches=top_match_job_ids,
            config_snapshot_ref=account_context.config_version,
            storage_path=storage_path,
        )
    )
    dependencies.structured_logger.info(
        account_id=account_id,
        run_id=run_id,
        stage="Report Compilation",
        message=f"Rapor derlendi ({len(included_job_ids)} ilan icerir).",
        extra={"included_job_ids_count": len(included_job_ids)},
    )

    # State Update (PRD adim 11): raporlanan ilanlarin report_appearances_count'u
    # artirilir; TUM bu calistirmada islenen EvaluatedJob'lar kalici hale getirilir.
    included_job_id_set = set(included_job_ids)
    for evaluated_job in evaluated_jobs:
        is_previously_tracked = evaluated_job.job_id in previous_by_job_id
        if evaluated_job.job_id in included_job_id_set:
            evaluated_job = evaluated_job.model_copy(
                update={"report_appearances_count": evaluated_job.report_appearances_count + 1}
            )
        _persist_evaluated_job(
            dependencies.evaluated_job_repository,
            evaluated_job,
            is_new=not is_previously_tracked,
        )

    dependencies.session.commit()  # atomic final state: evaluated_jobs + reports + run_logs
    dependencies.structured_logger.info(
        account_id=account_id,
        run_id=run_id,
        stage="State Update",
        message=f"Calistirma tamamlandi: {jobs_new} yeni, {jobs_closed} kapali.",
        extra={"jobs_new": jobs_new, "jobs_closed": jobs_closed, "status": str(run_log.status)},
    )
    return created_run_log


def run(
    account_id: UUID,
    dependencies: OrchestratorDependencies,
    trigger_type: TriggerType,
    now: datetime,
    lock_duration: timedelta,
    is_bootstrap: bool,
) -> RunLog:
    """Bir `AccountContext` icin tam bir pipeline dongusunu uctan uca
    calistirir (Roadmap M9.3 "Beklenen Sonuc": "Tek bir fonksiyon
    cagrisi... uctan uca calistirir").

    Hesap dogrulamasi (`load_account_context()`) `RunLock.acquire()`'dan
    ONCE yapilir (independent review duzeltmesi, bkz. asagidaki not) - bu
    yuzden RunLock mesgulse `RunAlreadyInProgressError` firlatir (hicbir is
    yapilmadan, hicbir run_logs satiri yazilmadan). Pipeline ortasinda
    HERHANGI bir istisna yakalanirsa: o ana kadarki (henuz commit
    edilmemis) batch degisiklikler geri alinir, AYRI bir Failed run_logs
    satiri yazilir ve o satir donulur (istisna yeniden firlatilmaz -
    "Run basarisiz oldu" bir CAGRI SONUCUDUR, orchestrator'in kendi
    calismasinin cokmesi degil). RunLock her kosulda serbest birakilir.

    **Duzeltme notu (independent review bulgusu, Finding 1):** Ilk
    implementasyon `RunLock.acquire()`'i hesap dogrulamasindan ONCE
    cagiriyordu. `run_locks.account_id` `accounts.account_id`'ye bir
    FOREIGN KEY tasidigi icin (bkz. db/models.py RunLockOrm), var olmayan
    bir `account_id` ile `acquire()`'in kendi INSERT'i ham, yakalanmamis
    bir `IntegrityError` firlatiyordu - `load_account_context()`'in
    (config/loader.py, M2.2, degistirilmemis) tam da bu senaryo icin
    ozel olarak tasarlanmis, acik "Hesap bulunamadi" `ValueError`'i hic
    devreye girmiyordu (FR-15'in "sessiz hata olusmaz" ilkesini ihlal
    eden, TUTARSIZ bir hata yolu). Duzeltme: hesap dogrulamasi ARTIK
    `RunLock.acquire()`'dan ONCE yapilir - boylece gecersiz bir
    `account_id` icin ASLA `run_locks`'a dokunulmaz.

    ONEMLI: `run_logs.account_id` de AYNI turden bir FOREIGN KEY tasir
    (bkz. db/models.py RunLogOrm) - bu yuzden var olmayan bir hesap icin
    bir Failed `run_logs` satiri YAZILAMAZ (kaydedilecek gercek bir hesap
    yoktur); bu, `RunAlreadyInProgressError`'in "hicbir is denenmedi"
    ilkesiyle AYNI kategoridedir. Asagidaki `except` bloğu bu yuzden
    ONCE Failed run_logs satirini yazmayi DENER (var olan bir hesap icin
    diger TUM hata turlerinde - orn. eksik UserProfile/config profili -
    bu BASARILI olur, mevcut davranis DEGISMEZ); yalnizca bu YAZMA
    girisiminin KENDISI de bir `IntegrityError` ile basarisiz olursa
    (yalnizca "hesap hic var olmuyor" durumunda mumkun), orijinal, acik
    hata (orn. "Hesap bulunamadi") oldugu gibi yukari firlatilir.
    """
    run_id = uuid4()
    lock_owner = str(run_id)
    run_lock = RunLock(dependencies.session)
    lock_acquired = False

    try:
        account_context = load_account_context(account_id, dependencies.session)

        acquired = run_lock.acquire(account_id, lock_owner, now, lock_duration)
        if not acquired:
            raise RunAlreadyInProgressError(
                f"Hesap icin zaten bir calistirma suruyor: {account_id}"
            )
        lock_acquired = True
        dependencies.session.commit()

        return _run_pipeline(
            account_id=account_id,
            account_context=account_context,
            dependencies=dependencies,
            run_id=run_id,
            trigger_type=trigger_type,
            now=now,
            is_bootstrap=is_bootstrap,
        )
    except RunAlreadyInProgressError:
        raise
    except Exception as exc:  # noqa: BLE001 - TDD Section 20: merkezi hata siniflandirma noktasi
        dependencies.session.rollback()
        try:
            failed_run_log = dependencies.run_log_repository.create(
                RunLog(
                    run_id=run_id,
                    account_id=account_id,
                    trigger_type=trigger_type,
                    started_at=now,
                    ended_at=now,
                    status=RunStatus.FAILED,
                    error_detail=str(exc),
                )
            )
        except IntegrityError:
            # Hesabin KENDISI hic var olmuyorsa, run_logs.account_id'nin
            # KENDI FK kisiti geregi bir Failed satir dahi yazilamaz -
            # orijinal, acikca anlasilir hatayi (bkz. yukaridaki
            # docstring notu) oldugu gibi yukari firlat.
            dependencies.session.rollback()
            raise exc from None
        dependencies.session.commit()
        # TDD Section 19: "her ERROR, karsilik gelen run_logs.error_detail
        # alanini doldurmak ZORUNDADIR" - bu cagri VE `error_detail=str(exc)`
        # (yukarida) AYNI `exc` degerinden turer ve AYNI kod noktasinda
        # (Failed run_logs satiri BASARIYLA persist edildikten hemen sonra)
        # birlikte gerceklesir, boylece bu esleme yapisal olarak garanti
        # edilir (bkz. test_orchestrator.py'nin bu kuralı denetleyen testi).
        dependencies.structured_logger.error(
            account_id=account_id,
            run_id=run_id,
            stage="Run",
            message=str(exc),
        )
        return failed_run_log
    finally:
        if lock_acquired:
            run_lock.release(account_id, lock_owner)
            dependencies.session.commit()
