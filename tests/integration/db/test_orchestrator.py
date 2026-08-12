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
    """

    def __init__(
        self, cards_by_call: list[list[str]], validate_error: Exception | None = None
    ) -> None:
        self._cards_by_call = list(cards_by_call)
        self._validate_error = validate_error
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

    assert result.status == RunStatus.SUCCESS
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
    assert run_log_row.status == RunStatus.SUCCESS

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
    assert first_result.status == RunStatus.SUCCESS
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
    assert first_result.status == RunStatus.SUCCESS

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

    assert second_result.status == RunStatus.SUCCESS
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

    assert result.status == RunStatus.SUCCESS
    evaluated = dependencies.evaluated_job_repository.get_by_account_and_job(
        account.account_id, job_url
    )
    assert evaluated is not None
    assert evaluated.status == JobStatus.NEW
    assert evaluated.is_borderline is True
    assert evaluated.ai_match_score is not None


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

    assert result.status == RunStatus.SUCCESS
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
