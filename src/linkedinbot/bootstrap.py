"""Paylasilan composition-root mantigi (Roadmap M10.1, TDD Section 5/9).

TDD Section 5'in dosya agaci, `main.py` ve `cli.py`'yi EŞIT SEVIYEDE, AYRI
giris noktalari olarak tanimlar - main.py ("sürecin giriş noktası (scheduler
döngüsü)") ve cli.py ("manuel tetikleme / config doğrulama komutları").
M9.7'de bu modulun icerdigi mantik (`build_dependencies()`/`run_account()`)
`cli.py` icinde `_build_dependencies()` olarak insa edilmisti; M10.1'in
`main.py`'yi insa etmesiyle BIRLIKTE bagimsiz incelemede bulunan bir tasarim
bulgusu ortaya cikti: main.py'nin cli.py'den DOGRUDAN import etmesi, TDD'nin
bu iki dosyayi BIRBIRINDEN BAGIMSIZ tanimlayan mimarisiyle CELISEN yanal
(sideways) bir bagimlilik yaratirdi. Bu modul o bulgunun duzeltmesidir:
`cli.py` YALNIZCA CLI sunumundan (argparse, cikis kodlari, stdout/stderr)
sorumludur; `main.py` YALNIZCA uzun-omurlu zamanlayici surecinden
sorumludur; HER IKISI de bu module bagimlidir, BIRBIRLERINE DEGIL.

`run_account()`, `cli.py`'deki ONCEKI halinden farkli olarak `trigger_type:
TriggerType`'i ACIKCA bir parametre olarak alir (ONCEDEN `TriggerType.MANUAL`
sabit kodluydu) - `main.py`'nin zamanlanmis calistirmalari `TriggerType.SCHEDULED`
ile DOGRU isaretlemesi icin GEREKLIDIR; `cli.py`'nin kendi cagri noktasi
artik `TriggerType.MANUAL`'i acikca gecirir.

Bu modulun KENDISI hicbir yeni is mantigi ICERMEZ - yalnizca ZATEN onaylanmis
Port'lari/adaptorleri (M2.3, M3.1-M3.3, M5.1-M5.2, M8.3, M9.2, M9.5)
`OrchestratorDependencies`'e (M9.3) baglar ve `orchestrator.run()`'u
(degistirilmemis) cagirir.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from linkedinbot.adapters.linkedin.playwright_client import (
    check_session_is_valid,
    fetch_search_results_page,
    perform_interactive_login,
)
from linkedinbot.adapters.linkedin.session_manager import SessionManager
from linkedinbot.adapters.llm.anthropic_adapter import AnthropicLLMAdapter
from linkedinbot.adapters.llm.gateway import LLMGateway
from linkedinbot.adapters.llm.prompt_registry import PromptRegistry
from linkedinbot.adapters.reporting.filesystem_report_store import FilesystemReportStore
from linkedinbot.adapters.secrets.local_keyring_adapter import (
    LocalKeyringSecretsProvider,
    resolve_encryption_key,
)
from linkedinbot.config.loader import load_account_context
from linkedinbot.db.repositories.company_repository import SqlAlchemyCompanyRepository
from linkedinbot.db.repositories.company_score_repository import SqlAlchemyCompanyScoreRepository
from linkedinbot.db.repositories.evaluated_job_repository import SqlAlchemyEvaluatedJobRepository
from linkedinbot.db.repositories.job_repository import SqlAlchemyJobRepository
from linkedinbot.db.repositories.report_repository import SqlAlchemyReportRepository
from linkedinbot.db.repositories.run_log_repository import SqlAlchemyRunLogRepository
from linkedinbot.domain.run_log import RunLog, TriggerType
from linkedinbot.logging.structured_logger import StructuredLogger
from linkedinbot.ports.secrets_provider_port import SecretsProviderPort
from linkedinbot.run import orchestrator
from linkedinbot.run.orchestrator import OrchestratorDependencies

# PRD/TDD hicbir yerde bir "Lock Timeout" degeri tanimlamaz (bkz.
# run_lock.py modul dokumaninin ayni notu) - somut deger, orchestrator.run()'un
# ILK GERCEK cagiranlari olarak burada (M9.7, sonra M10.1) bir
# implementasyon-zamani karari olarak sabitlenir. `max_jobs_per_run`
# (varsayilan 200) kadar ilan icin LLM retry/backoff dahil gercekci bir
# ust sinir.
LOCK_DURATION = timedelta(hours=2)


def run_account(
    account_id: UUID,
    dependencies: OrchestratorDependencies,
    now: datetime,
    lock_duration: timedelta,
    trigger_type: TriggerType,
) -> RunLog:
    """`orchestrator.run()`'u cagirir (Roadmap M9.7 "Bileşenler: CLI, Run
    Orchestrator, RunLock" - RunLock burada AYRICA kontrol edilmez,
    `orchestrator.run()`'un KENDI ic RunLock kontrolu hem otomatik hem
    manuel yolun AYNI kilidi kullanmasini zaten garanti eder, bkz. TDD
    Section 12 "Hem otomatik hem manuel tetikleme aynı kilidi kontrol
    eder").

    `is_bootstrap`, `reporting/compiler.py`'nin KENDI dokumaninin
    ongordugu sekilde (FR-20/EDGE-13: "Job History Store" bu hesap icin
    bos mu) hesaplanir - `evaluated_job_repository.list_by_account()`,
    orchestrator.py'nin (M9.3, degistirilmemis) `previous_by_job_id`'yi
    olusturmak icin ZATEN kullandigi AYNI sorgudur; burada AYRI bir
    "Job History Store bos mu" kavrami ICAT EDILMEZ.

    `RunAlreadyInProgressError` DAHIL hicbir istisna burada yakalanmaz -
    `orchestrator.run()`'un kendi davranisi degistirilmeden cagirana
    (`cli._run_run_command`/`main.py`'nin `on_trigger` geri-cagirmasi)
    sizar.
    """
    is_bootstrap = len(dependencies.evaluated_job_repository.list_by_account(account_id)) == 0
    return orchestrator.run(
        account_id, dependencies, trigger_type, now, lock_duration, is_bootstrap
    )


def _require_secret(secrets_provider: SecretsProviderPort, key: str) -> str:
    """`SecretsProviderPort.get()`'in "sessizce bir varsayilan uretmez,
    None doner" ilkesinin (bkz. secrets_provider_port.py) cagiran
    tarafinda nasil ele alinacagina karar verir - eksik bir secret icin
    acik, anahtar adini isimlendiren bir `ValueError` firlatir."""
    value = secrets_provider.get(key)
    if value is None:
        raise ValueError(
            f"Secret bulunamadi: '{key}'. LocalKeyringSecretsProvider.set() "
            "ile once ayarlanmalidir (bkz. TDD Section 24)."
        )
    return value


def build_dependencies(
    account_id: UUID,
    session: Session,
    config_dir: Path,
    reports_dir: Path,
    secrets_file: Path,
) -> OrchestratorDependencies:
    """TDD Section 9 "Süreç modeli"nin hem manuel ("ayrı bir kısa ömürlü
    süreç olarak Orchestrator'ı doğrudan çağırır", M9.7/`cli.py`) hem
    zamanlanmis ("main.py") yolu icin ORTAK composition root'u.

    `account_context.config_profile.thresholds`, `AnthropicLLMAdapter`'in
    retry parametrelerini SAGLAMAK icin burada yuklenir - `orchestrator.run()`
    KENDISI de dahili olarak ayni hesabi tekrar yukler (degistirilmemis,
    M9.3); bu kucuk bir tekrardir ama KACINILMAZDIR, cunku adaptor INSA
    EDILMEDEN once retry parametrelerine ihtiyac vardir ve `orchestrator.run()`
    kendi config yuklemesini disaridan bir parametre olarak KABUL ETMEZ
    (imzasi degistirilmez, "Preserve existing public APIs").
    """
    account_context = load_account_context(account_id, session)
    thresholds = account_context.config_profile.thresholds

    secrets_provider = LocalKeyringSecretsProvider(secrets_file, resolve_encryption_key())
    api_key = _require_secret(secrets_provider, "anthropic_api_key")

    linkedin_port = SessionManager(
        session,
        secrets_provider,
        perform_interactive_login,
        check_session_is_valid,
        fetch_search_results_page,
    )
    llm_gateway = LLMGateway(
        llm_provider=AnthropicLLMAdapter(
            api_key=api_key,
            llm_retry_attempts=thresholds.llm_retry_attempts,
            retry_base_delay_ms=thresholds.retry_base_delay_ms,
            retry_max_delay_ms=thresholds.retry_max_delay_ms,
        ),
        prompt_registry=PromptRegistry(prompts_dir=config_dir / "prompts"),
    )

    return OrchestratorDependencies(
        session=session,
        linkedin_port=linkedin_port,
        llm_gateway=llm_gateway,
        report_store=FilesystemReportStore(reports_dir),
        job_repository=SqlAlchemyJobRepository(session),
        company_repository=SqlAlchemyCompanyRepository(session),
        company_score_repository=SqlAlchemyCompanyScoreRepository(session),
        evaluated_job_repository=SqlAlchemyEvaluatedJobRepository(session),
        report_repository=SqlAlchemyReportRepository(session),
        run_log_repository=SqlAlchemyRunLogRepository(session),
        structured_logger=StructuredLogger(level=os.environ.get("LOG_LEVEL", "INFO")),
    )
