"""main.py'nin `_on_trigger`'inin oturum-uyarisi mekanizmasini GERCEK bir
DB, GERCEK bir SessionManager ve GERCEK orchestrator.run() uzerinden
dogrulayan entegrasyon testleri (Roadmap M12 Faz 5'te canli bir zamanlanmis
calistirmaya karsi kesfedilen kusurun regresyon koruyucusu).

`tests/unit/test_main.py`, `main.py`'nin kendi modul dokumanindaki KASITLI
tasarim geregi DB'ye hic dokunmayan sahtelerle calisir - ancak M12'nin
kendi bulgusu tam da bu sahtelerin GIZLEYEMEDIGI iki katmanli bir
entegrasyon uyusmazligiydi: (1) `orchestrator.run()`, `SessionInvalidError`
DAHIL her istisnayi yakalayip bir Failed RunLog ile NORMAL doner - hic
firlatmaz; (2) `SessionManager.validate()`'in `session_status=EXPIRED`
yazisi yalnizca bir `flush()`'tir - `orchestrator.run()`'un KENDI
`except Exception` dalindaki `rollback()`, bu flush'i HENUZ commit
edilmeden GERI ALIR (bu ikinci bulgu, main.py'nin ilk taslak duzeltmesi
BILE bu dosyanin GERCEK-DB entegrasyon testiyle sinanana kadar
GOZDEN KACMISTI). Hicbiri, gercek bir DB + gercek bir SessionManager +
gercek orchestrator.run() OLMADAN gozlemlenemez - bu dosya o bosluğu
dolduran uctan uca senaryoyu icerir.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from linkedinbot import main
from linkedinbot.adapters.linkedin.session_manager import SessionManager
from linkedinbot.adapters.reporting.filesystem_report_store import FilesystemReportStore
from linkedinbot.db.models import (
    AccountConfigProfileOrm,
    AccountOrm,
    LinkedInSessionOrm,
    SessionStatus,
    UserProfileOrm,
)
from linkedinbot.db.repositories.company_repository import SqlAlchemyCompanyRepository
from linkedinbot.db.repositories.company_score_repository import SqlAlchemyCompanyScoreRepository
from linkedinbot.db.repositories.evaluated_job_repository import SqlAlchemyEvaluatedJobRepository
from linkedinbot.db.repositories.job_repository import SqlAlchemyJobRepository
from linkedinbot.db.repositories.report_repository import SqlAlchemyReportRepository
from linkedinbot.db.repositories.run_log_repository import SqlAlchemyRunLogRepository
from linkedinbot.logging.structured_logger import StructuredLogger
from linkedinbot.ports.secrets_provider_port import SecretsProviderPort
from linkedinbot.run.orchestrator import OrchestratorDependencies


class _FakeSecretsProvider(SecretsProviderPort):
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        self._store[key] = value


def _seed_account_context(db_session: Session, account_id: UUID) -> None:
    now = datetime.now(UTC)
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
            validated_at=now,
            target_criteria={
                "locations": ["Istanbul"],
                "departments": {"Sales & Business Development": ["Sales Executive"]},
                "experience_levels": ["Entry Level"],
                "workplace_types": ["On-site"],
            },
            weights_ai_match={
                "department_role_relevance": 0.35,
                "experience_level_fit": 0.15,
                "location_fit": 0.10,
                "company_quality_contribution": 0.25,
                "career_goal_alignment": 0.15,
            },
            weights_company_quality={
                "brand_reputation_prestige": 0.25,
                "company_scale": 0.20,
                "career_development_training_culture": 0.20,
                "sector_position": 0.15,
                "corporate_stability": 0.10,
                "external_signals": 0.10,
            },
            thresholds={
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
            schedule={"interval_days": 2, "jitter_minutes": 30},
            collection_limits={"max_jobs_per_run": 1},
            notification_settings={"enabled": False, "channels": []},
            report_format_settings={
                "format": "Markdown",
                "template": "default",
                "top_matches_count": 10,
                "language": "en",
            },
            prompt_template_refs={
                "department_matching": "department_matching.prompt.md",
                "experience_inference": "experience_inference.prompt.md",
                "company_scoring": "company_scoring.prompt.md",
                "ai_match_rationale": "ai_match_rationale.prompt.md",
            },
        )
    )
    db_session.flush()


def test_on_trigger_writes_alert_and_durably_persists_expired_status_for_a_live_check_failure(
    db_session: Session, account: AccountOrm, tmp_path, monkeypatch
):
    # Roadmap M12'nin gercek bulgusunu birebir yeniden uretir: ONCEDEN
    # GECERLI (committed) bir oturum, canli kontrol (`session_validity_checker`)
    # basarisiz olunca gecersizlesir. `_on_trigger`, hem uyari dosyasini
    # YAZMALI hem de DB'nin `session_status`'unu KALICI olarak EXPIRED
    # birakmalidir (orchestrator.run()'un kendi rollback'ine RAGMEN).
    account_id = account.account_id
    secrets_provider = _FakeSecretsProvider()
    secrets_provider.set("linkedin_storage_state:existing", json.dumps({"cookies": []}))
    db_session.add(
        LinkedInSessionOrm(
            account_id=account_id,
            encrypted_storage_state_ref="linkedin_storage_state:existing",
            session_status=SessionStatus.VALID,
            last_validated_at=datetime.now(UTC),
        )
    )
    _seed_account_context(db_session, account_id)
    # `_on_trigger` kendi AYRI engine/session'ini acar - bu yuzden onceki
    # yazilarin GORULEBILMESI icin burada commit edilmesi SARTTIR (aksi
    # halde farkli bir DB baglantisi henuz-commit-edilmemis satirlari GOREMEZ).
    db_session.commit()

    def _fake_build_dependencies(account_id, session, config_dir, reports_dir, secrets_file):
        session_manager = SessionManager(
            session,
            secrets_provider,
            lambda: {"cookies": []},
            lambda storage_state: False,  # canli kontrol BASARISIZ
            lambda storage_state, location, keywords, page: [],
        )
        return OrchestratorDependencies(
            session=session,
            linkedin_port=session_manager,
            llm_gateway=None,
            report_store=FilesystemReportStore(reports_dir),
            job_repository=SqlAlchemyJobRepository(session),
            company_repository=SqlAlchemyCompanyRepository(session),
            company_score_repository=SqlAlchemyCompanyScoreRepository(session),
            evaluated_job_repository=SqlAlchemyEvaluatedJobRepository(session),
            report_repository=SqlAlchemyReportRepository(session),
            run_log_repository=SqlAlchemyRunLogRepository(session),
            structured_logger=StructuredLogger(log_file_path=tmp_path / "app.log"),
        )

    monkeypatch.setattr(main, "build_dependencies", _fake_build_dependencies)

    on_trigger = main._make_on_trigger(tmp_path, tmp_path, tmp_path / "secrets.json")
    on_trigger(account_id)  # firlatmamali - Failed bir calistirma NORMAL doner

    alert_path = tmp_path / "NEEDS_LOGIN.txt"
    assert alert_path.exists()
    assert str(account_id) in alert_path.read_text(encoding="utf-8")

    db_session.expire_all()
    row = db_session.get(LinkedInSessionOrm, account_id)
    assert row.session_status == SessionStatus.EXPIRED
