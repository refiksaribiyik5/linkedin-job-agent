"""run/orchestrator.py icin entegrasyon testleri (Roadmap M9.3).

Roadmap M9.3 "Beklenen Sonuc": "Tek bir fonksiyon cagrisi, tum pipeline'i
(session validation -> ... -> logging) uctan uca calistirir." "Tamamlanma
Dogrulamasi": "orkestrator ile tam bir dry-run yapilir; her asamanin
dogru sirada ve dogru veriyle calistigi (mock repository'lerle)
dogrulanir; kasitli olarak tetiklenen bir orta-pipeline hatasinin
evaluated_jobs/reports/run_logs durumunu bozmadigini (rollback) dogrulayan
bir test eklenir."

Bu modul GERCEK bir DB oturumuna karsi test eder (`tests/integration/db/
conftest.py`'nin paylasilan `db_session`/`account` fixture'lari) - hem
gercek SQLAlchemy repository'lerin (M1.3/M9.2) hem de RunLock'un (M9.1)
gercek atomiklik davranisini sinamak icin gereklidir; "mock repository"
yerine gercek repository'ler + sahte (fake) LinkedInPort/LLMGateway
kullanilir (bu projenin `tests/unit/adapters/llm/test_gateway.py`'deki
`_ScriptedProvider` deseniyle AYNI yaklasim).

Test verisi kasitli olarak KUCUK tutulur (tek lokasyon, tek departman
kumesi, `max_jobs_per_run=1`): `collection/collector.py`'nin (M3.5)
RateLimiter'i, ilk istek HARIC her LinkedIn istegi arasinda gercek
`time.sleep()` cagirir ve orchestrator, `collect_raw_job_cards()`'a
enjekte edilebilir bir sahte `sleep` GECMEZ (bkz. orchestrator.py
`_COLLECTION_DELAY_SECONDS` modul sabiti) - bu yuzden testlerin
gereksiz yere yavaslamamasi icin senaryolar, birden fazla LinkedIn
istegi GEREKTIRMEYECEK sekilde (tek sorgu, `max_jobs_per_run=1` ile ilk
istekte kapanma) kurgulanir.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from linkedinbot.adapters.reporting.filesystem_report_store import FilesystemReportStore
from linkedinbot.db.models import AccountConfigProfileOrm, RunLogOrm, UserProfileOrm
from linkedinbot.db.repositories.company_repository import SqlAlchemyCompanyRepository
from linkedinbot.db.repositories.company_score_repository import SqlAlchemyCompanyScoreRepository
from linkedinbot.db.repositories.evaluated_job_repository import SqlAlchemyEvaluatedJobRepository
from linkedinbot.db.repositories.job_repository import SqlAlchemyJobRepository
from linkedinbot.db.repositories.report_repository import SqlAlchemyReportRepository
from linkedinbot.db.repositories.run_log_repository import SqlAlchemyRunLogRepository
from linkedinbot.domain.evaluated_job import FilterResult, JobStatus, MatchRationaleItem
from linkedinbot.domain.run_log import RunStatus, TriggerType
from linkedinbot.ports.linkedin_port import LinkedInPort, SessionInvalidError
from linkedinbot.ports.report_store_port import ReportStorePort
from linkedinbot.run import orchestrator
from linkedinbot.run.run_lock import RunLock
from linkedinbot.scoring.ai_matching import AIMatchRationaleInference, CareerGoalAlignmentInference
from linkedinbot.scoring.company_scoring import CompanyScoringInference, DimensionAssessment

NOW = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)
LOCK_DURATION = timedelta(hours=1)


def _unique_job_and_card() -> tuple[str, str, str]:
    """`job_postings`/`companies` (Shared/Reference tablolar, PRD Section
    15.0) `account_id`'ye gore izole DEGILDIR - ve orchestrator, TDD
    Section 17'nin "eager cache" stratejisi geregi bunlari GERCEKTEN
    commit eder (bkz. orchestrator.py modul dokumani). Bu yuzden
    `db_session` fixture'inin "test sonunda rollback" izolasyonu bu
    tablolar icin GECERLI DEGILDIR - HER testin kendi, digerleriyle
    CAKISMAYAN benzersiz `job_id`/`company_id` degerleri kullanmasi
    gerekir (aksi halde bir test digerinin ONCEDEN commit ettigi veriyi
    gorur/onunla cakisir).
    """
    unique = uuid4().hex
    job_url = f"https://www.linkedin.com/jobs/view/{unique}"
    company = f"Acme Corp {unique}"
    card = f"""
<div>
  <div class="job-card-title">Sales Executive - Entry Level Program</div>
  <div class="job-card-company">{company}</div>
  <div class="job-card-location">Istanbul, Turkey</div>
  <div class="job-card-date">2 days ago</div>
  <div class="job-card-description">
    Entry Level opportunity to develop key accounts and drive business growth.
  </div>
  <a class="job-card-link" href="{job_url}">View</a>
</div>
"""
    return job_url, company, card


def _valid_config_profile_data() -> dict:
    """`tests/integration/db/test_loader.py::_valid_config_profile_data`'nin
    ayni AGIRLIK setini (validate_config()'un %100 toplam kuralini
    saglayan, zaten dogrulanmis degerler) kullanir; yalnizca
    target_criteria/collection_limits, orchestrator testlerinin TEK
    sorgu/TEK sayfa senaryosuna uyacak sekilde (bkz. modul dokumani -
    RateLimiter gercek sleep'i onlemek icin) daraltilmistir.
    """
    return {
        "target_criteria": {
            "locations": ["Istanbul"],
            "departments": {"Sales & Business Development": ["Sales Executive"]},
            "experience_levels": ["Entry Level"],
            "workplace_types": ["On-site"],
        },
        "weights_ai_match": {
            "department_role_relevance": 0.35,
            "experience_level_fit": 0.15,
            "location_fit": 0.10,
            "company_quality_contribution": 0.25,
            "career_goal_alignment": 0.15,
        },
        "weights_company_quality": {
            "brand_reputation_prestige": 0.25,
            "company_scale": 0.20,
            "career_development_training_culture": 0.20,
            "sector_position": 0.15,
            "corporate_stability": 0.10,
            "external_signals": 0.10,
        },
        "thresholds": {
            "company_quality_score": 50,
            "ai_match_score": 60,
            "department_confidence": 0.65,
            "department_confidence_tolerance": 0.05,
            "borderline_band_width": 5,
            "company_score_reevaluation_window_days": 30,
            "linkedin_retry_attempts": 3,
            "llm_retry_attempts": 3,
            "retry_base_delay_ms": 500,
            "retry_max_delay_ms": 8000,
            "linkedin_consecutive_failure_threshold": 5,
        },
        "schedule": {"interval_days": 2, "jitter_minutes": 30},
        "collection_limits": {"max_jobs_per_run": 1},
        "notification_settings": {"enabled": False, "channels": []},
        "report_format_settings": {
            "format": "Markdown",
            "template": "default",
            "top_matches_count": 10,
            "language": "en",
        },
        "prompt_template_refs": {
            "department_matching": "department_matching.prompt.md",
            "experience_inference": "experience_inference.prompt.md",
            "company_scoring": "company_scoring.prompt.md",
            "ai_match_rationale": "ai_match_rationale.prompt.md",
        },
    }


def _seed_account_context(db_session: Session, account_id: UUID) -> None:
    db_session.add(
        UserProfileOrm(
            account_id=account_id,
            career_goals="Grow into a business development leadership role.",
            skills_summary="Sales, account management, negotiation.",
            preferences_dealbreakers={"excluded_companies": [], "excluded_job_ids": []},
        )
    )
    db_session.add(
        AccountConfigProfileOrm(
            account_id=account_id,
            config_version=1,
            is_active=True,
            validated_at=NOW,
            **_valid_config_profile_data(),
        )
    )
    db_session.flush()


class _FakeLinkedInPort(LinkedInPort):
    """`search_jobs_page()` her cagrida, `cards_by_call`'dan bir sonraki
    ham HTML karti listesini "pop" eder; liste tukenirse bos liste doner
    (dogal sayfalama sonu). `validate_error` verilirse `validate()` bunu
    firlatir (Session Validation basarisizligini simule etmek icin).
    `search_error` verilirse (M9.4), `search_jobs_page()` HER cagrida bu
    hatayi firlatir - devre kesicinin (Section 21) orkestrasyon-seviyesi
    entegrasyonunu (Partial run_log) test etmek icin.
    """

    def __init__(
        self,
        cards_by_call: list[list[str]],
        validate_error: Exception | None = None,
        search_error: Exception | None = None,
    ) -> None:
        self._cards_by_call = list(cards_by_call)
        self._validate_error = validate_error
        self._search_error = search_error
        self.search_calls = 0

    def ensure_session(self, account_id: UUID) -> None:
        raise NotImplementedError

    def validate(self, account_id: UUID) -> None:
        if self._validate_error is not None:
            raise self._validate_error

    def search_jobs_page(
        self, account_id: UUID, location: str, keywords: str, page: int
    ) -> list[str]:
        self.search_calls += 1
        if self._search_error is not None:
            raise self._search_error
        if self._cards_by_call:
            return self._cards_by_call.pop(0)
        return []


class _ScriptedLLMGateway:
    """`filtering/department_filter.py::_FakeLLMGateway` (M6.4) ile AYNI
    desen: `template_name`'e gore sabit, gecerli bir Pydantic yaniti
    doner. Beklenmedik bir sablon istenirse test'in acikca basarisiz
    olmasi icin `AssertionError` firlatir (sessizce yanlis bir yanit
    donmez).
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(self, template_name, response_model, model, **template_variables):
        self.calls.append(template_name)
        if template_name == "department_matching":
            from linkedinbot.filtering.department_filter import DepartmentMatchInference

            return DepartmentMatchInference(
                matched_cluster="Sales & Business Development",
                confidence=0.9,
                reasoning="Directly matches the Sales & Business Development cluster.",
            )
        if template_name == "career_goal_alignment":
            return CareerGoalAlignmentInference(
                score=0.8, explanation="Strong alignment with stated career goals."
            )
        if template_name == "company_scoring":
            dimension = DimensionAssessment(score=80.0, justification="Well-regarded employer.")
            return CompanyScoringInference(
                brand_reputation_prestige=dimension,
                company_scale=dimension,
                career_development_training_culture=dimension,
                sector_position=dimension,
                corporate_stability=dimension,
                external_signals=dimension,
            )
        if template_name == "ai_match_rationale":
            return AIMatchRationaleInference(
                items=[
                    MatchRationaleItem(
                        component="Department/Role Relevance",
                        value="0.90",
                        explanation="Strong department match.",
                    ),
                    MatchRationaleItem(
                        component="Experience Level Fit",
                        value="Yes",
                        explanation="Matches an accepted entry-level posting.",
                    ),
                    MatchRationaleItem(
                        component="Location Fit",
                        value="Yes",
                        explanation="Located in Istanbul.",
                    ),
                ]
            )
        raise AssertionError(f"Unexpected template_name in test: {template_name!r}")


class _RaisingReportStore(ReportStorePort):
    """`save()`'i her zaman basarisiz kilan sahte ReportStore -
    orta-pipeline hata/rollback senaryosunu (Roadmap M9.3 Tamamlanma
    Dogrulamasi) tetiklemek icin kullanilir."""

    def save(self, account_id, report_id, generated_at, content):
        raise OSError("simulated disk failure")


class _CapturingStructuredLogger:
    """Gercek dosya G/C'si yapmayan, tum `.info()/.warning()/.error()`
    cagrilarini bellekte tutan sahte StructuredLogger (Roadmap M9.5).
    `structured_logger.py`'nin kendi davranisi (redaksiyon, best-effort,
    JSON bicimi) `tests/unit/logging/test_structured_logger.py`'de ZATEN
    ayrintili sekilde test edilir - burada YALNIZCA orchestrator'in
    DOGRU asamalarda/seviyelerde cagri yaptigini dogrulamak icin
    kullanilir (TDD Section 19'un "her ERROR run_logs.error_detail'i
    doldurmak ZORUNDADIR" kurali dahil)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def info(self, *, account_id, run_id, stage, message, extra=None):
        self.calls.append(
            {
                "level": "INFO",
                "account_id": account_id,
                "run_id": run_id,
                "stage": stage,
                "message": message,
                "extra": extra,
            }
        )

    def warning(self, *, account_id, run_id, stage, message, extra=None):
        self.calls.append(
            {
                "level": "WARNING",
                "account_id": account_id,
                "run_id": run_id,
                "stage": stage,
                "message": message,
                "extra": extra,
            }
        )

    def error(self, *, account_id, run_id, stage, message, extra=None):
        self.calls.append(
            {
                "level": "ERROR",
                "account_id": account_id,
                "run_id": run_id,
                "stage": stage,
                "message": message,
                "extra": extra,
            }
        )


def _make_dependencies(
    db_session: Session,
    tmp_path,
    linkedin_port: LinkedInPort,
    llm_gateway,
    report_store: ReportStorePort | None = None,
) -> orchestrator.OrchestratorDependencies:
    return orchestrator.OrchestratorDependencies(
        session=db_session,
        linkedin_port=linkedin_port,
        llm_gateway=llm_gateway,
        report_store=report_store or FilesystemReportStore(tmp_path),
        job_repository=SqlAlchemyJobRepository(db_session),
        company_repository=SqlAlchemyCompanyRepository(db_session),
        company_score_repository=SqlAlchemyCompanyScoreRepository(db_session),
        evaluated_job_repository=SqlAlchemyEvaluatedJobRepository(db_session),
        report_repository=SqlAlchemyReportRepository(db_session),
        run_log_repository=SqlAlchemyRunLogRepository(db_session),
        structured_logger=_CapturingStructuredLogger(),
    )


def test_first_run_creates_new_job_scores_report_and_success_run_log(
    db_session: Session, account, tmp_path
):
    job_url, company, card = _unique_job_and_card()
    _seed_account_context(db_session, account.account_id)
    dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[card]]), _ScriptedLLMGateway()
    )

    result = orchestrator.run(
        account.account_id, dependencies, TriggerType.MANUAL, NOW, LOCK_DURATION, is_bootstrap=True
    )

    # `max_jobs_per_run=1` (test fixture, _valid_config_profile_data) cap'e
    # tam bu tek kartla ulasilir - M9.4 "unified completeness" duzeltmesi
    # geregi `collection_capped=True` HER ZAMAN `is_complete=False` anlamina
    # gelir, dolayisiyla Run PARTIAL'dir (SUCCESS DEGIL).
    assert result.status == RunStatus.PARTIAL
    assert result.partial_reason is not None
    assert result.jobs_collected == 1
    assert result.jobs_filtered == 1
    assert result.jobs_new == 1
    assert result.jobs_closed == 0
    assert result.collection_capped is True

    evaluated = dependencies.evaluated_job_repository.get_by_account_and_job(
        account.account_id, job_url
    )
    assert evaluated is not None
    assert evaluated.status == JobStatus.NEW
    assert evaluated.department_cluster == "Sales & Business Development"
    assert evaluated.ai_match_score is not None
    assert evaluated.match_rationale is not None
    assert evaluated.report_appearances_count == 1

    job_posting = dependencies.job_repository.get_by_id(job_url)
    assert job_posting is not None
    assert job_posting.company_id == company

    company_score = dependencies.company_score_repository.get_by_key(company, None, 1)
    assert company_score is not None
    assert company_score.score_total == 80.0

    run_log_row = dependencies.run_log_repository.get_by_id(account.account_id, result.run_id)
    assert run_log_row is not None
    assert run_log_row.status == RunStatus.PARTIAL

    report = dependencies.report_repository.get_by_run_id(account.account_id, result.run_id)
    assert report is not None
    assert report.included_job_ids == [job_url]
    assert report.storage_path.exists()
    content = report.storage_path.read_text(encoding="utf-8")
    assert "Bootstrap" in content
    assert "Sales Executive" in content


def test_job_missing_from_a_later_run_is_marked_closed(db_session: Session, account, tmp_path):
    job_url, _company, card = _unique_job_and_card()
    _seed_account_context(db_session, account.account_id)

    first_run_dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[card]]), _ScriptedLLMGateway()
    )
    first_result = orchestrator.run(
        account.account_id,
        first_run_dependencies,
        TriggerType.MANUAL,
        NOW,
        LOCK_DURATION,
        is_bootstrap=True,
    )
    # Ilk calistirma, tek kartla max_jobs_per_run=1 cap'ine ulasir - M9.4
    # "unified completeness" duzeltmesi geregi PARTIAL'dir. Ikinci
    # calistirma (asagida) BOS bir sayfa doner - cap HIC vurulmaz, hicbir
    # sorgu basarisiz olmaz - is_complete=True kalir, kapali-ilan tespiti
    # normal sekilde calisir.
    assert first_result.status == RunStatus.PARTIAL
    assert first_result.jobs_new == 1

    second_now = NOW + timedelta(days=2)
    second_run_dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[]]), _ScriptedLLMGateway()
    )
    second_result = orchestrator.run(
        account.account_id,
        second_run_dependencies,
        TriggerType.SCHEDULED,
        second_now,
        LOCK_DURATION,
        is_bootstrap=False,
    )

    assert second_result.status == RunStatus.SUCCESS
    assert second_result.jobs_collected == 0
    assert second_result.jobs_closed == 1
    assert second_result.jobs_new == 0

    evaluated = second_run_dependencies.evaluated_job_repository.get_by_account_and_job(
        account.account_id, job_url
    )
    assert evaluated is not None
    assert evaluated.status == JobStatus.CLOSED


def test_a_seen_job_reappearing_in_top_matches_still_renders_a_company_score(
    db_session: Session, account, tmp_path
):
    # Regression: a SEEN job is reused WHOLESALE from the previous
    # EvaluatedJob (`_reused_seen_job()`) and never goes through
    # `_evaluate_new_or_updated_job()` - so its company is never added to
    # THIS run's `company_scores_this_run` cache. But `rank_top_matches()`
    # (ranking/ranker.py, degistirilmemis) considers SEEN jobs eligible
    # for Top Matches (unlike department sections, which only take NEW/
    # UPDATED) - so a strong, unchanged SEEN job can still land in
    # `top_matches` on a LATER run. `compile_report()`'s
    # `_render_top_match_line()` then looks up the job's CompanyScore in
    # `company_scores_by_id` and raises `ValueError` if it is missing
    # (bkz. reporting/compiler.py `_company_quality_score()`) - the
    # orchestrator must backfill a CompanyScore for every company that
    # can actually appear in the compiled report, not only for
    # freshly-filtered New/Updated jobs.
    job_url, company, card = _unique_job_and_card()
    _seed_account_context(db_session, account.account_id)

    first_run_dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[card]]), _ScriptedLLMGateway()
    )
    first_result = orchestrator.run(
        account.account_id,
        first_run_dependencies,
        TriggerType.MANUAL,
        NOW,
        LOCK_DURATION,
        is_bootstrap=True,
    )
    # max_jobs_per_run=1 cap'ine ilk kartla ulasilir - PARTIAL (M9.4).
    assert first_result.status == RunStatus.PARTIAL

    # Ikinci calistirma AYNI karti (degismemis icerik) doner - ilan SEEN
    # olarak siniflandirilir ve wholesale yeniden kullanilir.
    second_now = NOW + timedelta(days=2)
    second_run_dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[card]]), _ScriptedLLMGateway()
    )
    second_result = orchestrator.run(
        account.account_id,
        second_run_dependencies,
        TriggerType.SCHEDULED,
        second_now,
        LOCK_DURATION,
        is_bootstrap=False,
    )

    # Ayni sekilde cap'e ulasilir - PARTIAL (M9.4).
    assert second_result.status == RunStatus.PARTIAL
    evaluated = second_run_dependencies.evaluated_job_repository.get_by_account_and_job(
        account.account_id, job_url
    )
    assert evaluated is not None
    assert evaluated.status == JobStatus.SEEN
    assert evaluated.ai_match_score is not None

    report = second_run_dependencies.report_repository.get_by_run_id(
        account.account_id, second_result.run_id
    )
    assert report is not None
    assert job_url in report.top_matches
    content = report.storage_path.read_text(encoding="utf-8")
    assert "Company Quality" in content
    assert company in content


def test_run_raises_when_the_account_is_already_locked(db_session: Session, account, tmp_path):
    _, _company, card = _unique_job_and_card()
    _seed_account_context(db_session, account.account_id)
    lock = RunLock(db_session)
    assert lock.acquire(account.account_id, "someone-else", NOW, LOCK_DURATION) is True
    db_session.flush()

    dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[card]]), _ScriptedLLMGateway()
    )

    with pytest.raises(orchestrator.RunAlreadyInProgressError):
        orchestrator.run(
            account.account_id,
            dependencies,
            TriggerType.MANUAL,
            NOW,
            LOCK_DURATION,
            is_bootstrap=True,
        )

    assert dependencies.evaluated_job_repository.list_by_account(account.account_id) == []
    run_log_count = (
        db_session.query(RunLogOrm).filter(RunLogOrm.account_id == account.account_id).count()
    )
    assert run_log_count == 0


def test_run_with_a_nonexistent_account_id_raises_a_clear_error_not_a_raw_fk_violation(
    db_session: Session, tmp_path
):
    # Regression (independent review, Finding 1): RunLock.acquire() used to
    # run BEFORE account-existence validation (load_account_context()).
    # run_locks.account_id carries a FOREIGN KEY to accounts.account_id, so
    # a nonexistent account_id made RunLock.acquire()'s own INSERT raise a
    # raw, uncaught psycopg IntegrityError instead of the clean, already-
    # established "Hesap bulunamadi" ValueError that load_account_context()
    # (config/loader.py, M2.2, unchanged) is specifically designed to raise
    # for exactly this case.
    #
    # Note: a Failed run_logs row cannot be written for a nonexistent
    # account either - run_logs.account_id carries the SAME kind of FK
    # (verified directly against SqlAlchemyRunLogRepository.create()) - so
    # there is no valid account to record a "failed run" against in the
    # first place. The fix's observable contract is therefore a clean,
    # uncaught ValueError (same principle as RunAlreadyInProgressError's
    # "hicbir is denenmedi" - nothing was attempted, so nothing is logged),
    # not a persisted run_logs row.
    nonexistent_account_id = uuid4()
    dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([]), _ScriptedLLMGateway()
    )

    with pytest.raises(ValueError, match="Hesap bulunamadi"):
        orchestrator.run(
            nonexistent_account_id,
            dependencies,
            TriggerType.MANUAL,
            NOW,
            LOCK_DURATION,
            is_bootstrap=True,
        )

    # Ne run_locks ne de run_logs'a hicbir satir yazilmis olmamalidir - kilit
    # hic alinmamis olmalidir (hesap gecersizken hicbir islem denenmemistir).
    run_log_count = (
        db_session.query(RunLogOrm)
        .filter(RunLogOrm.account_id == nonexistent_account_id)
        .count()
    )
    assert run_log_count == 0


def test_session_invalid_error_leaves_no_state_and_writes_a_failed_run_log(
    db_session: Session, account, tmp_path
):
    job_url, _company, card = _unique_job_and_card()
    _seed_account_context(db_session, account.account_id)
    validate_error = SessionInvalidError("LinkedIn session expired")
    dependencies = _make_dependencies(
        db_session,
        tmp_path,
        _FakeLinkedInPort([[card]], validate_error=validate_error),
        _ScriptedLLMGateway(),
    )

    result = orchestrator.run(
        account.account_id, dependencies, TriggerType.MANUAL, NOW, LOCK_DURATION, is_bootstrap=True
    )

    assert result.status == RunStatus.FAILED
    assert "LinkedIn session expired" in result.error_detail
    assert dependencies.evaluated_job_repository.list_by_account(account.account_id) == []
    assert dependencies.job_repository.get_by_id(job_url) is None

    run_log_row = dependencies.run_log_repository.get_by_id(account.account_id, result.run_id)
    assert run_log_row is not None
    assert run_log_row.status == RunStatus.FAILED


def test_mid_pipeline_failure_rolls_back_the_batch_but_keeps_eager_writes_and_logs_failure(
    db_session: Session, account, tmp_path
):
    # Roadmap M9.3 Tamamlanma Dogrulamasi: "kasitli olarak tetiklenen bir
    # orta-pipeline hatasinin evaluated_jobs/reports/run_logs durumunu
    # bozmadigini (rollback) dogrulayan bir test." `report_store.save()`,
    # job_postings/companies/company_scores EAGER commit edildikten (TDD
    # Section 17) SONRA, ama evaluated_jobs/reports/run_logs BATCH
    # commit'inden ONCE cagrilir - bu yuzden bu, "eager write hayatta
    # kalir, batch write geri alinir" ayrimini dogrudan sinar.
    job_url, company, card = _unique_job_and_card()
    _seed_account_context(db_session, account.account_id)
    dependencies = _make_dependencies(
        db_session,
        tmp_path,
        _FakeLinkedInPort([[card]]),
        _ScriptedLLMGateway(),
        report_store=_RaisingReportStore(),
    )

    result = orchestrator.run(
        account.account_id, dependencies, TriggerType.MANUAL, NOW, LOCK_DURATION, is_bootstrap=True
    )

    assert result.status == RunStatus.FAILED
    assert "simulated disk failure" in result.error_detail

    # Eager-committed veri (job_postings/companies/company_scores) HAYATTA
    # KALIR - bu, TDD Section 17'nin "eager cache, atomic final state"
    # stratejisinin dogrudan sonucudur.
    assert dependencies.job_repository.get_by_id(job_url) is not None
    assert dependencies.company_repository.get_by_id(company) is not None
    assert dependencies.company_score_repository.get_by_key(company, None, 1) is not None

    # Batch-committed veri (evaluated_jobs/reports) HICBIRI olusmaz.
    assert dependencies.evaluated_job_repository.list_by_account(account.account_id) == []
    assert dependencies.report_repository.get_by_run_id(account.account_id, result.run_id) is None

    # Tam olarak BIR Failed run_logs satiri yazilir (FR-15 - sessiz hata olusmaz).
    run_log_row = dependencies.run_log_repository.get_by_id(account.account_id, result.run_id)
    assert run_log_row is not None
    assert run_log_row.status == RunStatus.FAILED
    run_log_count = (
        db_session.query(RunLogOrm).filter(RunLogOrm.account_id == account.account_id).count()
    )
    assert run_log_count == 1


def test_a_failed_run_produces_exactly_one_error_log_matching_error_detail(
    db_session: Session, account, tmp_path
):
    # Roadmap M9.5, TDD Section 19: "her ERROR, karsilik gelen
    # run_logs.error_detail alanini doldurmak ZORUNDADIR - bu kural bir
    # test ile denetlenir." Bu test tam olarak o kuralı denetler: bir Run
    # basarisiz oldugunda, StructuredLogger tam olarak BIR ERROR-seviyeli
    # cagri alir ve o cagrinin mesaji, persist edilen `run_logs.error_detail`
    # ile BIREBIR eslesir.
    job_url, _company, card = _unique_job_and_card()
    _seed_account_context(db_session, account.account_id)
    validate_error = SessionInvalidError("LinkedIn session expired")
    dependencies = _make_dependencies(
        db_session,
        tmp_path,
        _FakeLinkedInPort([[card]], validate_error=validate_error),
        _ScriptedLLMGateway(),
    )

    result = orchestrator.run(
        account.account_id, dependencies, TriggerType.MANUAL, NOW, LOCK_DURATION, is_bootstrap=True
    )

    assert result.status == RunStatus.FAILED
    error_calls = [
        call for call in dependencies.structured_logger.calls if call["level"] == "ERROR"
    ]
    assert len(error_calls) == 1
    assert error_calls[0]["message"] == result.error_detail
    assert error_calls[0]["account_id"] == account.account_id
    assert error_calls[0]["run_id"] == result.run_id


def test_a_successful_run_logs_info_at_each_stage_boundary_and_no_error(
    db_session: Session, account, tmp_path
):
    job_url, _company, card = _unique_job_and_card()
    _seed_account_context(db_session, account.account_id)
    dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[card]]), _ScriptedLLMGateway()
    )

    result = orchestrator.run(
        account.account_id, dependencies, TriggerType.MANUAL, NOW, LOCK_DURATION, is_bootstrap=True
    )

    # max_jobs_per_run=1 (test fixture) cap'ine tek kartla ulasilir -
    # PARTIAL (M9.4 "unified completeness"), Failed DEGIL.
    assert result.status == RunStatus.PARTIAL
    calls = dependencies.structured_logger.calls
    assert [call["level"] for call in calls] == [
        "INFO",  # Session Validation
        "INFO",  # Collection
        "WARNING",  # EDGE-9 kismi sonuc (collection_capped -> is_complete=False)
        "INFO",  # History
        "INFO",  # Evaluation
        "INFO",  # Report Compilation
        "INFO",  # State Update
    ]
    assert all(call["account_id"] == account.account_id for call in calls)
    assert all(call["run_id"] == result.run_id for call in calls)


def test_a_job_only_matching_the_department_confidence_tolerance_band_is_borderline(
    db_session: Session, account, tmp_path
):
    # Gap B amendment (department_confidence_tolerance) dogrudan sinanir:
    # LLM guveni esigin (0.65) ALTINDA ama tolerans bandinin (0.05)
    # icindeyse (>= 0.60), ilan yine de GECER ve is_borderline=True olarak
    # isaretlenir (filtering/pipeline.py, degistirilmemis).
    job_url, _company, card = _unique_job_and_card()
    _seed_account_context(db_session, account.account_id)

    class _BorderlineLLMGateway(_ScriptedLLMGateway):
        def generate(self, template_name, response_model, model, **template_variables):
            if template_name == "department_matching":
                from linkedinbot.filtering.department_filter import DepartmentMatchInference

                return DepartmentMatchInference(
                    matched_cluster="Sales & Business Development",
                    confidence=0.62,
                    reasoning="Related but not a precise title match.",
                )
            return super().generate(template_name, response_model, model, **template_variables)

    dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[card]]), _BorderlineLLMGateway()
    )

    result = orchestrator.run(
        account.account_id, dependencies, TriggerType.MANUAL, NOW, LOCK_DURATION, is_bootstrap=True
    )

    # max_jobs_per_run=1 cap'ine tek kartla ulasilir - PARTIAL (M9.4).
    assert result.status == RunStatus.PARTIAL
    evaluated = dependencies.evaluated_job_repository.get_by_account_and_job(
        account.account_id, job_url
    )
    assert evaluated is not None
    assert evaluated.status == JobStatus.NEW
    assert evaluated.is_borderline is True
    assert evaluated.ai_match_score is not None


def test_circuit_breaker_trip_during_collection_produces_a_partial_run_with_a_real_report(
    db_session: Session, account, tmp_path
):
    # M9.4 uctan uca: devre kesici tetiklenince Orchestrator, PRD Section
    # 15.7 geregi HALA gecerli bir rapor ureten, evaluated_jobs/reports/
    # run_logs'u NORMAL sekilde commit eden bir Partial run_log doner -
    # Failed run_log'un (tam rollback) AKSINE. `linkedin_retry_attempts=1`
    # ve `linkedin_consecutive_failure_threshold=1`, tek sorgulu test
    # fixture'inde (bkz. _valid_config_profile_data) devre kesicinin ILK
    # cagrida, HICBIR gercek `time.sleep` olmadan tetiklenmesini saglar.
    db_session.add(
        UserProfileOrm(
            account_id=account.account_id,
            career_goals="Grow into a business development leadership role.",
            skills_summary="Sales, account management, negotiation.",
            preferences_dealbreakers={"excluded_companies": [], "excluded_job_ids": []},
        )
    )
    config_data = _valid_config_profile_data()
    config_data["thresholds"]["linkedin_retry_attempts"] = 1
    config_data["thresholds"]["linkedin_consecutive_failure_threshold"] = 1
    db_session.add(
        AccountConfigProfileOrm(
            account_id=account.account_id,
            config_version=1,
            is_active=True,
            validated_at=NOW,
            **config_data,
        )
    )
    db_session.flush()

    dependencies = _make_dependencies(
        db_session,
        tmp_path,
        _FakeLinkedInPort([], search_error=RuntimeError("simulated LinkedIn outage")),
        _ScriptedLLMGateway(),
    )

    result = orchestrator.run(
        account.account_id, dependencies, TriggerType.MANUAL, NOW, LOCK_DURATION, is_bootstrap=True
    )

    assert result.status == RunStatus.PARTIAL
    assert result.partial_reason is not None
    assert result.jobs_collected == 0
    assert result.error_detail is None  # error_detail Failed'e ozeldir (M9.4)

    run_log_row = dependencies.run_log_repository.get_by_id(account.account_id, result.run_id)
    assert run_log_row is not None
    assert run_log_row.status == RunStatus.PARTIAL
    assert run_log_row.partial_reason == result.partial_reason

    report = dependencies.report_repository.get_by_run_id(account.account_id, result.run_id)
    assert report is not None
    assert report.storage_path.exists()


def test_circuit_breaker_trip_does_not_falsely_close_previously_seen_jobs(
    db_session: Session, account, tmp_path
):
    # Regression (self-review bulgusu, gercek defect): `diff_job_postings()`
    # (M4.2, degistirilmemis) "current_scan'de gorunmeyen HER onceki ilan
    # kapanmistir" varsayar - bu varsayim yalnizca TAM bir tarama icin
    # gecerlidir. Devre kesici `raw_cards=[]` ile ERKEN donduginde, bu HIC
    # BIR SEKILDE "butun onceden bilinen ilanlar artik kapali" anlamina
    # GELMEZ - yalnizca bu calistirmada yeniden dogrulanamadiklari
    # anlamina gelir. Duzeltme oncesi, TEK bir gecici LinkedIn kesintisi
    # hesabin TUM acik ilanlarini yanlislikla Closed isaretleyip
    # raporlardan sessizce dusururdu (FR-10 ihlali).
    job_url, _company, card = _unique_job_and_card()
    _seed_account_context(db_session, account.account_id)

    first_run_dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[card]]), _ScriptedLLMGateway()
    )
    first_result = orchestrator.run(
        account.account_id,
        first_run_dependencies,
        TriggerType.MANUAL,
        NOW,
        LOCK_DURATION,
        is_bootstrap=True,
    )
    # max_jobs_per_run=1 cap'ine tek kartla ulasilir - PARTIAL (M9.4).
    assert first_result.status == RunStatus.PARTIAL

    config_row = (
        db_session.query(AccountConfigProfileOrm)
        .filter(
            AccountConfigProfileOrm.account_id == account.account_id,
            AccountConfigProfileOrm.is_active.is_(True),
        )
        .one()
    )
    config_row.thresholds = {
        **config_row.thresholds,
        "linkedin_retry_attempts": 1,
        "linkedin_consecutive_failure_threshold": 1,
    }
    flag_modified(config_row, "thresholds")
    db_session.flush()

    second_now = NOW + timedelta(days=2)
    second_run_dependencies = _make_dependencies(
        db_session,
        tmp_path,
        _FakeLinkedInPort([], search_error=RuntimeError("simulated LinkedIn outage")),
        _ScriptedLLMGateway(),
    )
    second_result = orchestrator.run(
        account.account_id,
        second_run_dependencies,
        TriggerType.SCHEDULED,
        second_now,
        LOCK_DURATION,
        is_bootstrap=False,
    )

    assert second_result.status == RunStatus.PARTIAL
    assert second_result.jobs_closed == 0

    evaluated = second_run_dependencies.evaluated_job_repository.get_by_account_and_job(
        account.account_id, job_url
    )
    assert evaluated is not None
    assert evaluated.status != JobStatus.CLOSED
    assert evaluated.status == JobStatus.NEW


def test_collection_capped_run_does_not_falsely_close_jobs_from_unreached_queries(
    db_session: Session, account, tmp_path
):
    # Regression (independent review, Finding 1 follow-up): FR-21's own
    # acceptance criterion frames a capped collection as "kesildi" (cut
    # short) - textually the SAME kind of incomplete scan as a circuit-
    # breaker trip, just via a DIFFERENT trigger. The is_partial-only
    # guard added for the circuit-breaker case did NOT cover this path: a
    # run that stops early because max_jobs_per_run (FR-21) was reached
    # (status stays plain SUCCESS - not even Partial!) can silently mark
    # a genuinely-still-open job Closed, simply because its query was
    # never reached before the cap.
    job_url_a, _company_a, card_a = _unique_job_and_card()
    unique_b = uuid4().hex
    job_url_b = f"https://www.linkedin.com/jobs/view/{unique_b}"
    company_b = f"Other Corp {unique_b}"
    card_b = f"""
<div>
  <div class="job-card-title">Marketing Specialist - Entry Level</div>
  <div class="job-card-company">{company_b}</div>
  <div class="job-card-location">Istanbul, Turkey</div>
  <div class="job-card-date">2 days ago</div>
  <div class="job-card-description">
    Entry Level marketing role.
  </div>
  <a class="job-card-link" href="{job_url_b}">View</a>
</div>
"""
    db_session.add(
        UserProfileOrm(
            account_id=account.account_id,
            career_goals="Grow into a business development leadership role.",
            skills_summary="Sales, account management, negotiation.",
            preferences_dealbreakers={"excluded_companies": [], "excluded_job_ids": []},
        )
    )
    config_data = _valid_config_profile_data()
    # IKI departman sorgusu: cap ILK sorguda vurulunca IKINCI sorgu hic
    # denenmeyecek - bu, bug'in gercek tetikleyicisidir.
    config_data["target_criteria"]["departments"] = {
        "Sales & Business Development": ["Sales Executive"],
        "Marketing": ["Marketing Specialist"],
    }
    config_data["collection_limits"]["max_jobs_per_run"] = 200
    db_session.add(
        AccountConfigProfileOrm(
            account_id=account.account_id,
            config_version=1,
            is_active=True,
            validated_at=NOW,
            **config_data,
        )
    )
    db_session.flush()

    # Run 1: cap yuksek (200) - her iki sorgu da dogal olarak tukenir, her
    # iki ilan da olusturulur. Bos sayfa listeleri, her sorgunun kendi
    # dogal sayfalama sonunu temsil eder (bkz. _FakeLinkedInPort - sirali
    # bir kuyruktan "pop" eder, sorgudan BAGIMSIZ).
    first_run_dependencies = _make_dependencies(
        db_session,
        tmp_path,
        _FakeLinkedInPort([[card_a], [], [card_b], []]),
        _ScriptedLLMGateway(),
    )
    first_result = orchestrator.run(
        account.account_id,
        first_run_dependencies,
        TriggerType.MANUAL,
        NOW,
        LOCK_DURATION,
        is_bootstrap=True,
    )
    assert first_result.status == RunStatus.SUCCESS
    assert first_result.jobs_new == 2

    # Cap'i dusur - Sales sorgusunun ILK karti cap'e ulasir, Marketing
    # sorgusu bu calistirmada HIC denenmez.
    config_row = (
        db_session.query(AccountConfigProfileOrm)
        .filter(
            AccountConfigProfileOrm.account_id == account.account_id,
            AccountConfigProfileOrm.is_active.is_(True),
        )
        .one()
    )
    config_row.collection_limits = {**config_row.collection_limits, "max_jobs_per_run": 1}
    flag_modified(config_row, "collection_limits")
    db_session.flush()

    second_now = NOW + timedelta(days=2)
    second_run_dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[card_a]]), _ScriptedLLMGateway()
    )
    second_result = orchestrator.run(
        account.account_id,
        second_run_dependencies,
        TriggerType.SCHEDULED,
        second_now,
        LOCK_DURATION,
        is_bootstrap=False,
    )

    # M9.4 "unified completeness" duzeltmesi: `collection_capped=True` ARTIK
    # HER ZAMAN `is_complete=False` (dolayisiyla Run PARTIAL) anlamina
    # gelir - onceki tasarimda (bu regresyonun asil bulundugu round) capped
    # bir calistirma yanlislikla plain SUCCESS kaliyordu.
    assert second_result.status == RunStatus.PARTIAL
    assert second_result.partial_reason is not None
    assert second_result.collection_capped is True
    assert second_result.jobs_closed == 0

    evaluated_b = second_run_dependencies.evaluated_job_repository.get_by_account_and_job(
        account.account_id, job_url_b
    )
    assert evaluated_b is not None
    assert evaluated_b.status != JobStatus.CLOSED
    assert evaluated_b.status == JobStatus.NEW


class _QueryAwareLinkedInPort(LinkedInPort):
    """`_FakeLinkedInPort` (bu dosyanin ana sahtesi) cagri-SIRASI ile
    anahtarlanir ve `search_error` TUM cagrilara uygulanir - bu, TEK bir
    sorgunun basarisiz olup DIGERININ basarili olmasi gereken bir
    senaryoyu (asagidaki test) modelleyemez. Bu sahte, `(location,
    keywords)` cifti ile anahtarlanir - unit seviyesindeki
    `tests/unit/collection/test_collector.py::_FakeLinkedInPort`'un
    sorgu-anahtarli deseniyle AYNI fikir, ama entegrasyon testinin kendi
    ihtiyaci icin (bu dosyanin konvansiyonuyla tutarli, dosyalar arasi
    sahte PAYLASILMAZ) burada YEREL olarak tanimlanir.
    """

    def __init__(
        self,
        cards_by_query: dict[tuple[str, str], list[list[str]]],
        always_fail_queries: frozenset[tuple[str, str]],
    ) -> None:
        self._cards_by_query = {k: list(v) for k, v in cards_by_query.items()}
        self._always_fail_queries = always_fail_queries
        self.queries_attempted: set[tuple[str, str]] = set()

    def ensure_session(self, account_id: UUID) -> None:
        raise NotImplementedError

    def validate(self, account_id: UUID) -> None:
        pass

    def search_jobs_page(
        self, account_id: UUID, location: str, keywords: str, page: int
    ) -> list[str]:
        key = (location, keywords)
        self.queries_attempted.add(key)
        if key in self._always_fail_queries:
            raise RuntimeError("simulated transient LinkedIn failure for this query")
        pages = self._cards_by_query.get(key, [])
        return pages[page] if page < len(pages) else []


def test_query_retry_exhaustion_below_circuit_breaker_threshold_does_not_falsely_close_jobs(
    db_session: Session, account, tmp_path
):
    # Regression (independent review, THIRD production bug found - root
    # cause of the M9.4 "unified completeness" redesign): a query whose
    # page ALWAYS fails exhausts ALL of its retry attempts, but if the
    # resulting consecutive-failure count stays BELOW
    # `linkedin_consecutive_failure_threshold`, the circuit breaker never
    # trips - collection treats it as "failed but continue" (identical to
    # a natural empty-page ending) and moves on to the next query. Before
    # the "unified completeness" redesign, this left ZERO trace in the
    # final CollectionResult: neither `is_partial` nor `collection_capped`
    # became True, so the closed-job-detection guard never engaged and a
    # genuinely-still-open job (whose ONLY query failed this run) was
    # silently marked Closed - with the run reporting plain SUCCESS, no
    # signal anything went wrong at all.
    job_url_a, _company_a, card_a = _unique_job_and_card()
    unique_b = uuid4().hex
    job_url_b = f"https://www.linkedin.com/jobs/view/{unique_b}"
    company_b = f"Other Corp {unique_b}"
    card_b = f"""
<div>
  <div class="job-card-title">Marketing Specialist - Entry Level</div>
  <div class="job-card-company">{company_b}</div>
  <div class="job-card-location">Istanbul, Turkey</div>
  <div class="job-card-date">2 days ago</div>
  <div class="job-card-description">
    Entry Level marketing role.
  </div>
  <a class="job-card-link" href="{job_url_b}">View</a>
</div>
"""
    db_session.add(
        UserProfileOrm(
            account_id=account.account_id,
            career_goals="Grow into a business development leadership role.",
            skills_summary="Sales, account management, negotiation.",
            preferences_dealbreakers={"excluded_companies": [], "excluded_job_ids": []},
        )
    )
    config_data = _valid_config_profile_data()
    # IKI departman sorgusu: Run 2'de Sales sorgusu TAMAMEN basarisiz
    # olacak, Marketing sorgusu basarili kalacak.
    config_data["target_criteria"]["departments"] = {
        "Sales & Business Development": ["Sales Executive"],
        "Marketing": ["Marketing Specialist"],
    }
    config_data["collection_limits"]["max_jobs_per_run"] = 200
    db_session.add(
        AccountConfigProfileOrm(
            account_id=account.account_id,
            config_version=1,
            is_active=True,
            validated_at=NOW,
            **config_data,
        )
    )
    db_session.flush()

    # Run 1: her iki sorgu da dogal olarak tukenir, her iki ilan da
    # olusturulur (bu ilerideki Sales ilaninin YANLISLIKLA kapanmadigini
    # dogrulamak icin bir "onceden acik" durumu kurar).
    first_run_dependencies = _make_dependencies(
        db_session,
        tmp_path,
        _FakeLinkedInPort([[card_a], [], [card_b], []]),
        _ScriptedLLMGateway(),
    )
    first_result = orchestrator.run(
        account.account_id,
        first_run_dependencies,
        TriggerType.MANUAL,
        NOW,
        LOCK_DURATION,
        is_bootstrap=True,
    )
    assert first_result.status == RunStatus.SUCCESS
    assert first_result.jobs_new == 2

    # Run 2: Sales sorgusu HER ZAMAN basarisiz olur (`linkedin_retry_attempts=1`
    # ile TEK denemede tukenir, gercek sleep olmadan) - ama devre kesici
    # esigi (5, fixture varsayilani, DEGISTIRILMEDI) TEK bir basarisiz
    # sorguyla ASILMAZ, dolayisiyla devre kesici HIC TETIKLENMEZ. Marketing
    # sorgusu normal sekilde calisir ve basarili olur.
    config_row = (
        db_session.query(AccountConfigProfileOrm)
        .filter(
            AccountConfigProfileOrm.account_id == account.account_id,
            AccountConfigProfileOrm.is_active.is_(True),
        )
        .one()
    )
    config_row.thresholds = {**config_row.thresholds, "linkedin_retry_attempts": 1}
    flag_modified(config_row, "thresholds")
    db_session.flush()

    second_now = NOW + timedelta(days=2)
    second_port = _QueryAwareLinkedInPort(
        cards_by_query={("Istanbul", '"Marketing Specialist"'): [[card_b], []]},
        always_fail_queries=frozenset({("Istanbul", '"Sales Executive"')}),
    )
    second_run_dependencies = _make_dependencies(
        db_session, tmp_path, second_port, _ScriptedLLMGateway()
    )
    second_result = orchestrator.run(
        account.account_id,
        second_run_dependencies,
        TriggerType.SCHEDULED,
        second_now,
        LOCK_DURATION,
        is_bootstrap=False,
    )

    # Devre kesici tetiklenmedi (breaker esigi asilmadi) VE cap'e ulasilmadi
    # (max_jobs_per_run=200) - ama Sales sorgusu HICBIR ZAMAN basariyla
    # taranamadigi icin Run yine de PARTIAL'dir ("unified completeness").
    assert second_result.status == RunStatus.PARTIAL
    assert second_result.partial_reason is not None
    assert second_result.collection_capped is False
    assert second_result.jobs_closed == 0
    # Marketing sorgusu, Sales'in basarisizligindan BAGIMSIZ olarak yine
    # de denendi (devre kesici tetiklenmedigi icin toplama DEVAM ETTI).
    assert ("Istanbul", '"Marketing Specialist"') in second_port.queries_attempted

    evaluated_a = second_run_dependencies.evaluated_job_repository.get_by_account_and_job(
        account.account_id, job_url_a
    )
    assert evaluated_a is not None
    assert evaluated_a.status != JobStatus.CLOSED
    assert evaluated_a.status == JobStatus.NEW


def test_blacklisted_company_is_excluded_without_scoring(db_session: Session, account, tmp_path):
    # FR-19: Blacklist reddi digerlerinden AYRI, ozel JobStatus.EXCLUDED
    # durumuna gider (bkz. orchestrator.py modul dokumani) - ve LLM'e HIC
    # gidilmez (Blacklist zincirin en basindadir, M6.1).
    job_url, company, card = _unique_job_and_card()
    db_session.add(
        UserProfileOrm(
            account_id=account.account_id,
            career_goals="Grow into a business development leadership role.",
            skills_summary="Sales, account management, negotiation.",
            preferences_dealbreakers={
                "excluded_companies": [company],
                "excluded_job_ids": [],
            },
        )
    )
    db_session.add(
        AccountConfigProfileOrm(
            account_id=account.account_id,
            config_version=1,
            is_active=True,
            validated_at=NOW,
            **_valid_config_profile_data(),
        )
    )
    db_session.flush()

    llm_gateway = _ScriptedLLMGateway()
    dependencies = _make_dependencies(
        db_session, tmp_path, _FakeLinkedInPort([[card]]), llm_gateway
    )

    result = orchestrator.run(
        account.account_id, dependencies, TriggerType.MANUAL, NOW, LOCK_DURATION, is_bootstrap=True
    )

    # max_jobs_per_run=1 cap'ine tek kartla ulasilir - PARTIAL (M9.4).
    assert result.status == RunStatus.PARTIAL
    assert result.jobs_filtered == 0

    evaluated = dependencies.evaluated_job_repository.get_by_account_and_job(
        account.account_id, job_url
    )
    assert evaluated is not None
    assert evaluated.status == JobStatus.EXCLUDED
    assert evaluated.ai_match_score is None
    assert evaluated.filter_result_detail["blacklist"] == FilterResult(
        passed=False, reason=f"Company '{company}' is on the exclusion blacklist."
    )
    # Blacklist ilk filtredir - hicbir LLM cagrisi yapilmamis olmalidir.
    assert llm_gateway.calls == []
