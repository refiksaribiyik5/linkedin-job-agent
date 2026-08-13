"""LinkedInBot CLI (TDD Section 5) - manuel komutlar.

M1.4: `seed` komutu eklenir - V1'in tek hesabini, kullanici profilini ve
ilk (config_version=1, is_active=true) config profilini
`config/system.defaults.yaml` + `config/accounts/default.account.yaml`
dosyalarindan olusturur (Roadmap M1.4). Manuel tetikleme icin bir `run`
komutu M9.7'nin ("CLI Genişletmesi (Manuel Tetikleme)") kapsamidir - bu
dosyanin M1.4 doneminde yazilan ONCEKI bir notu bunu yanlislikla M9.6'ya
atfediyordu (M9.6/M9.7 ayrimi henuz netlesmeden yazilmis bir tahmin);
M9.6 yalnizca zamanlama MEKANIZMASINI (`ports/scheduler_port.py`,
`adapters/scheduling/apscheduler_adapter.py`) kurar, bu dosyaya HICBIR
SEY eklemez - bu yuzden `cli.py`, ayri bir `scripts/seed.py` yerine
burada baslatilir (TDD Section 5'in dosya agacinda zaten `cli.py`
ayrilmistir, `scripts/` diye bir dizin hic yoktur).

M2.4: `config validate` komutu eklenir - `--config-dir` ile verilen bir
dizindeki AYNI iki YAML dosyasini (`seed`'in okudugu dosyalarla birebir
ayni ikili) okuyup M2.1'in `validate_config()`'una (sema + agirlik-toplami
is kurallari) verir ve sonucu bir çıkış koduyla (0=gecerli, 1=gecersiz)
raporlar. Roadmap M2.4'un "Tamamlanma Dogrulamasi" satiri acikca "bilinen
iyi ve kotu config DOSYALARIYLA manuel calistirma" der - bu KASITLI olarak
M2.2'nin `load_account_context()`'ini (DB'deki AKTIF config'i dogrulayan,
ayri bir kavram) KULLANMAZ; kullanici bu iki yorumu (dosya-tabanli vs.
DB-tabanli) acikca degerlendirip dosya-tabanli yorumu onaylamistir.

Bu modul, M2.1/M2.2'nin tam config sema/dogrulama/oncelik-zinciri
mantigini ONCEDEN UYGULAMAZ - yalnizca iki YAML dosyasini okuyup birlestirip
DB'ye bir kere yazan (`seed`) veya sadece dogrulayan (`config validate`)
minimal islemlerdir (bkz. `_deep_merge`, `seed`, `validate_config_files`
fonksiyonlarinin dokumanlari).

M9.7: `run` komutu eklenir - FR-12'nin manuel tetiklemesini, otomatik
cizelgeden bagimsiz olarak ekler. Bagimsiz dogrulama sonrasi onaylanan
karar geregi yalnizca `--account <id>` desteklenir (TDD Section 12'nin
"veya V1'de argumansiz" parantezi betimleyici bir ornektir, M9.7'nin
KENDI kabul kriterlerinde YER ALMAZ - bkz. asagidaki `run` bolumunun
kendi notu). Bu komut, `_build_dependencies()` araciligiyla TDD Section
9'un "ayrı bir kısa ömürlü süreç olarak Orchestrator'ı doğrudan çağırır"
tanimladigi composition root'u kurar - `main.py`'nin (henuz insa
edilmemis) zamanlanmis yol icin kuracagi sekle benzer, ama SADECE bu
dosyadan (manuel tetikleme) ibarettir.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
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
from linkedinbot.config.schema import AccountConfigProfile
from linkedinbot.config.validator import ConfigValidationError, validate_config
from linkedinbot.db.engine import create_db_engine, create_session_factory
from linkedinbot.db.models import AccountConfigProfileOrm
from linkedinbot.db.repositories.account_repository import SqlAlchemyAccountRepository
from linkedinbot.db.repositories.company_repository import SqlAlchemyCompanyRepository
from linkedinbot.db.repositories.company_score_repository import SqlAlchemyCompanyScoreRepository
from linkedinbot.db.repositories.evaluated_job_repository import SqlAlchemyEvaluatedJobRepository
from linkedinbot.db.repositories.job_repository import SqlAlchemyJobRepository
from linkedinbot.db.repositories.report_repository import SqlAlchemyReportRepository
from linkedinbot.db.repositories.run_log_repository import SqlAlchemyRunLogRepository
from linkedinbot.db.repositories.user_profile_repository import SqlAlchemyUserProfileRepository
from linkedinbot.domain.account import Account
from linkedinbot.domain.run_log import RunLog, RunStatus, TriggerType
from linkedinbot.domain.user_profile import Preferences, UserProfile
from linkedinbot.logging.structured_logger import StructuredLogger
from linkedinbot.ports.secrets_provider_port import SecretsProviderPort
from linkedinbot.run import orchestrator
from linkedinbot.run.orchestrator import OrchestratorDependencies, RunAlreadyInProgressError

# PRD/TDD hicbir yerde bir "Lock Timeout" degeri tanimlamaz (bkz.
# run_lock.py modul dokumaninin ayni notu) - somut deger, orchestrator.run()'un
# ILK GERCEK cagirani olarak burada (M9.7) bir implementasyon-zamani karari
# olarak sabitlenir. `max_jobs_per_run` (varsayilan 200) kadar ilan icin
# LLM retry/backoff dahil gercekci bir ust sinir.
_LOCK_DURATION = timedelta(hours=2)


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Ic-ice (nested) dict'ler icin basit birlestirme: `overrides`'taki her
    anahtar `base`'i ezer; iki tarafta da dict olan degerler recursive
    olarak birlestirilir (orn. `target_criteria.locations` ezilirken
    `target_criteria.departments` sistem varsayilanindan korunur).

    Bu, TDD Section 23'un tam oncelik zinciri (kod-ici varsayilanlar ->
    system.defaults.yaml -> DB'deki hesap profili -> ortam degiskenleri)
    DEGILDIR - yalnizca seed script'inin system.defaults.yaml + hesaba-ozel
    `account_config_overrides`'i BIR KEZ, seed anında birlestirmesi icin
    kullanilan minimal bir yardimcidir. Tam yukleme zinciri M2.2'nin isidir.
    """
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_config_files(config_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """`system.defaults.yaml` + `accounts/default.account.yaml` dosyalarini
    okur. `seed()` ve `validate_config_files()` tarafindan ortaklasa
    kullanilir - ikisi de TAM OLARAK ayni iki dosyaya ihtiyac duyar (seed
    account_seed'in TUMUNU - display_name/career_goals dahil - kullanirken,
    validate_config_files yalnizca `account_config_overrides`'i kullanir).

    Dosyalardan biri eksikse `FileNotFoundError` (yol adini iceren, Python'in
    kendi varsayilan mesaji) dogrudan yukari sizar - hem `seed` hem
    `config validate` icin bu, acik/anlasilir bir "dosya bulunamadi"
    basarisizligidir, ozel bir sarmalamaya ihtiyac yoktur.

    Ic-denetimde bulunan bulgu: sozdizimsel olarak bozuk YAML zaten acik
    bir `yaml.YAMLError` firlatiyordu (degisiklik gerekmedi), ama
    sozdizimsel olarak GECERLI ama bos veya mapping-olmayan bir dosya
    (`yaml.safe_load` boyle bir girdi icin `None` veya bir liste/skaler
    doner) asagi akiste (`_deep_merge`) baglamsiz bir `TypeError`'a
    neden oluyordu - `config validate`'in (M2.4) TAM OLARAK onlemesi
    gereken, kullanicinin "bilinen kotu config dosyasi" olarak deneyecegi
    en dogal senaryolardan biri. Burada acikca kontrol edilip, hangi
    dosyanin sorunlu oldugunu adiyla belirten bir `ValueError` firlatilir.
    """
    system_defaults_path = config_dir / "system.defaults.yaml"
    account_seed_path = config_dir / "accounts" / "default.account.yaml"
    system_defaults = yaml.safe_load(system_defaults_path.read_text())
    account_seed = yaml.safe_load(account_seed_path.read_text())
    if not isinstance(system_defaults, dict):
        raise ValueError(f"{system_defaults_path}: gecerli bir YAML sozlugu (mapping) icermiyor.")
    if not isinstance(account_seed, dict):
        raise ValueError(f"{account_seed_path}: gecerli bir YAML sozlugu (mapping) icermiyor.")
    return system_defaults, account_seed


def _load_config_profile_data(config_dir: Path) -> dict[str, Any]:
    """`_read_config_files()`'in okudugu ikiliyi, `account_config_overrides`'i
    sistem varsayilanlarinin uzerine deep-merge ederek TEK bir
    account_config_profiles-sekilli dict'e indirger (bkz. `seed()` ve
    `validate_config_files()`'in ikisinin de ihtiyac duydugu ortak sekil).
    """
    system_defaults, account_seed = _read_config_files(config_dir)
    overrides = account_seed.get("account_config_overrides", {})
    return _deep_merge(system_defaults, overrides)


def validate_config_files(config_dir: Path) -> AccountConfigProfile:
    """Roadmap M2.4: `config_dir` altindaki config dosyalarini (`seed()`'in
    okudugu AYNI iki dosya, ayni deep-merge mantigiyla) M2.1'in
    `validate_config()`'una (sema + agirlik-toplami is kurallari) verir.

    DB'ye hicbir sekilde dokunmaz - `seed`'in aksine burada bir `Session`
    parametresi YOKTUR, cunku dogrulanacak sey DB'ye henuz YAZILMAMIS bir
    ADAY dosya cifti (bkz. modul dokumaninin M2.4 notu).

    Basarisiz olursa `ConfigValidationError` (sema/is-kurali ihlalleri) veya
    `FileNotFoundError` (eksik dosya) firlatir - cagiran (`_run_config_validate_command`)
    bu ikisini yakalayip kullaniciya uygun bir cikis koduyla raporlar.
    """
    config_profile_data = _load_config_profile_data(config_dir)
    return validate_config(config_profile_data)


def _run_config_validate_command(config_dir: Path) -> int:
    """`linkedinbot config validate`'in gercek CLI cagrisi: `validate_config_files()`'i
    calistirir, basarili/basarisiz durumlari acik bir mesaj + dogru cikis
    koduyla (0=gecerli, 1=gecersiz) raporlar (Roadmap M2.4 "Beklenen Sonuc").

    Hata mesajlari stderr'e, basari mesaji stdout'a yazilir (standart CLI
    konvansiyonu - hatalar `2>/dev/null` ile ayri filtrelenebilsin diye).

    NOT: `ConfigValidationError`, `ValueError`'un bir alt sinifidir (bkz.
    config/validator.py) - bu yuzden `except ConfigValidationError` genel
    `except ValueError`'dan ONCE gelir; aksi halde Python'in ilk-eslesen-
    yakalar kurali geregi genel dal onu yakalar ve `.errors` listesindeki
    tek tek maddeler yerine tek bir genel mesaj basilirdi (bkz.
    test_run_config_validate_command_config_validation_error_not_swallowed_by_value_error).
    """
    try:
        validate_config_files(config_dir)
    except FileNotFoundError as exc:
        print(f"Config dosyasi bulunamadi: {exc}", file=sys.stderr)
        return 1
    except yaml.YAMLError as exc:
        print(f"Config dosyasi gecersiz YAML iceriyor: {exc}", file=sys.stderr)
        return 1
    except ConfigValidationError as exc:
        print(f"Config gecersiz ({config_dir}):", file=sys.stderr)
        for error in exc.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Config dosyasi gecersiz: {exc}", file=sys.stderr)
        return 1

    print(f"Config gecerli: {config_dir}")
    return 0


def seed(config_dir: Path, session: Session) -> Account:
    """Roadmap M1.4 "Beklenen Sonuç": bos bir veritabanina karsi calistirildiginda
    bir `accounts` satiri, bir `user_profiles` satiri ve
    `config_version=1, is_active=true` olan bir `account_config_profiles`
    satiri olusturur.

    Bu fonksiyon `session`'i CAGIRMAZ/COMMIT ETMEZ - transaction sinirini
    cagiran yonetir (bkz. `_run_seed_command`). Bu, M1.3'un repository
    test desenini (rollback edilen bir `db_session` fixture'i) burada da
    kullanabilmeyi saglar; aksi halde her test calistirmasi gercek
    dev veritabanina kalici, tekrar-eden hesaplar commit ederdi.

    Bu fonksiyon, populated bir veritabanina karsi TEKRAR calistirilmaya
    karsi guvenli DEGILDIR (idempotent degildir) - Roadmap M1.4'un
    Tamamlanma Dogrulamasi yalnizca bos bir veritabanini kapsar; bu
    kasitli bir sinirlamadir, V1'in tek seferlik bootstrap akisinin
    (bkz. M10.2) otesinde henuz bir gereksinim degildir.
    """
    system_defaults, account_seed = _read_config_files(config_dir)
    overrides = account_seed.get("account_config_overrides", {})
    config_profile_data = _deep_merge(system_defaults, overrides)

    now = datetime.now(UTC)
    account_repo = SqlAlchemyAccountRepository(session)
    user_profile_repo = SqlAlchemyUserProfileRepository(session)

    account = account_repo.create(
        Account(
            display_name=account_seed["display_name"],
            created_at=now,
            status=account_seed.get("status", "active"),
        )
    )

    user_profile_repo.create(
        account.account_id,
        UserProfile(
            career_goals=account_seed["career_goals"].strip(),
            skills_summary=account_seed["skills_summary"].strip(),
            preferences=Preferences(**account_seed.get("preferences", {})),
        ),
    )

    # account_config_profiles icin M1.3'te kasitli olarak henuz bir
    # repository/Port yoktur (AccountConfigProfile domain modeli
    # M2.1'de tanimlanacak) - bu tek satir dogrudan ORM ile yazilir
    # (bkz. M1.4 onay kaydi). TDD Section 15'in composite PK'sini
    # (account_id, config_version) dogrudan kullanir.
    config_profile = AccountConfigProfileOrm(
        account_id=account.account_id,
        config_version=1,
        target_criteria=config_profile_data["target_criteria"],
        weights_ai_match=config_profile_data["weights_ai_match"],
        weights_company_quality=config_profile_data["weights_company_quality"],
        thresholds=config_profile_data["thresholds"],
        schedule=config_profile_data["schedule"],
        collection_limits=config_profile_data["collection_limits"],
        notification_settings=config_profile_data["notification_settings"],
        report_format_settings=config_profile_data["report_format_settings"],
        prompt_template_refs=config_profile_data["prompt_template_refs"],
        is_active=True,
        # NOT: `validated_at`, bu satirin YAZILDIGI zamani tasir - FR-13'un
        # gercek sema/agirlik-toplami dogrulamasi (M2.1) burada henuz
        # CALISMAZ. Bu alanin "gercekten dogrulandi" degil "bu haliyle
        # kaydedildi" anlamina geldigi acikca not edilir; M2.1 kendi
        # dogrulamasini calistirdiginda bu alani gunceller.
        validated_at=now,
    )
    session.add(config_profile)
    session.flush()

    return account


def _run_seed_command(config_dir: Path) -> None:
    """`seed()`'in gercek CLI cagrisi icin sarmalayicisi: engine/session'i
    kurar, transaction sinirini (commit/rollback) yonetir.
    """
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    session: Session = session_factory()
    try:
        account = seed(config_dir, session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()

    print(f"Seed tamamlandi: account_id={account.account_id}")


# ---------------------------------------------------------------------------
# `run` (Roadmap M9.7, FR-12 manuel tetikleme). Bagimsiz dogrulama sonrasi
# onaylanan karar: yalnizca `--account <id>` desteklenir - TDD Section 12'nin
# "veya V1'de argumansiz" parantezi, M9.7'nin KENDI "Beklenen Sonuc"/
# "Tamamlanma Dogrulamasi" metninde YER ALMAZ ve FR-12'nin kabul kriterleri
# de CLI sozdizimine deginmez; bu betimleyici bir ornektir, zorunlu bir
# kabul kriteri degildir. Bu yuzden `AccountRepositoryPort`'a "tek hesabi
# bul" gibi yeni bir metod EKLENMEZ (M1.3'e bir Roadmap duzeltmesi
# gerektirmez).
# ---------------------------------------------------------------------------


def run_account(
    account_id: UUID,
    dependencies: OrchestratorDependencies,
    now: datetime,
    lock_duration: timedelta,
) -> RunLog:
    """Manuel tetiklemenin gercek isi: `orchestrator.run()`'u `TriggerType.MANUAL`
    ile cagirir (Roadmap M9.7 "Bileşenler: CLI, Run Orchestrator, RunLock" -
    RunLock burada AYRICA kontrol edilmez, `orchestrator.run()`'un KENDI
    ic RunLock kontrolu hem otomatik hem manuel yolun AYNI kilidi
    kullanmasini zaten garanti eder, bkz. TDD Section 12 "Hem otomatik hem
    manuel tetikleme aynı kilidi kontrol eder").

    `is_bootstrap`, `reporting/compiler.py`'nin KENDI dokumaninin
    ongordugu sekilde (FR-20/EDGE-13: "Job History Store" bu hesap icin
    bos mu) hesaplanir - `evaluated_job_repository.list_by_account()`,
    orchestrator.py'nin (M9.3, degistirilmemis) `previous_by_job_id`'yi
    olusturmak icin ZATEN kullandigi AYNI sorgudur; burada AYRI bir
    "Job History Store bos mu" kavrami ICAT EDILMEZ.

    `RunAlreadyInProgressError` DAHIL hicbir istisna burada yakalanmaz -
    `orchestrator.run()`'un kendi davranisi degistirilmeden cagirana
    (`_run_run_command`) sizar.
    """
    is_bootstrap = len(dependencies.evaluated_job_repository.list_by_account(account_id)) == 0
    return orchestrator.run(
        account_id, dependencies, TriggerType.MANUAL, now, lock_duration, is_bootstrap
    )


def _report_run_result(result: RunLog) -> int:
    """`run_account()`'in donen `RunLog`'unu kullaniciya raporlar (Roadmap
    M9.7 "Beklenen Sonuc"). Success/Partial HALA TAM TESEKKULLU bir
    sonuctur (PRD Section 15.7, M9.4'un "Partial bir hata DEGILDIR"
    ilkesi) - stdout'a yazilir, cikis kodu 0'dir. Yalnizca Failed
    stderr'e yazilir ve 1 doner (`config validate`'in 0=gecerli/1=gecersiz
    konvansiyonuyla tutarli)."""
    if result.status == RunStatus.FAILED:
        print(f"Calistirma basarisiz oldu: {result.error_detail}", file=sys.stderr)
        return 1

    summary = (
        f"Calistirma tamamlandi: durum={result.status.value}, "
        f"toplanan={result.jobs_collected}, filtrelenen={result.jobs_filtered}, "
        f"yeni={result.jobs_new}, kapanan={result.jobs_closed}"
    )
    if result.status == RunStatus.PARTIAL and result.partial_reason:
        summary += f" ({result.partial_reason})"
    print(summary)
    return 0


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


def _build_dependencies(
    account_id: UUID,
    session: Session,
    config_dir: Path,
    reports_dir: Path,
    secrets_file: Path,
) -> OrchestratorDependencies:
    """Roadmap M9.7'nin manuel tetikleme yolu icin somut composition
    root'u - TDD Section 9 "Süreç modeli"nin "ayrı bir kısa ömürlü süreç
    olarak Orchestrator'ı doğrudan çağırır" tanimladigi yol. `main.py`
    (TDD Section 5, henuz insa edilmemis) zamanlanmis yol icin AYNI sekli
    kuracaktir, ama bu fonksiyon M9.7'nin KENDI dosyasindan (cli.py)
    OTESINE gecmez (bkz. `ports/scheduler_port.py`/`apscheduler_adapter.py`
    modul dokumanlarinin "sahiplik sınırı" notlari, M9.6).

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


def _run_run_command(
    account_id: UUID, config_dir: Path, reports_dir: Path, secrets_file: Path
) -> int:
    """`linkedinbot run --account <id>`'in gercek CLI cagrisi (Roadmap M9.7).

    `orchestrator.run()` (dolayisiyla `run_account()`) KENDI transaction
    sinirini/commit'lerini yonetir (bkz. orchestrator.py modul dokumani,
    "eager cache, atomic final state") - bu yuzden burada basari yolunda
    AYRI bir `session.commit()` cagrisi YOKTUR (`seed()`'in aksine - o
    KENDI commit ETMEYEN bir fonksiyondur, transaction siniri cagirana
    birakilir). Hata yollarindaki `session.rollback()` savunma amaclidir:
    `orchestrator.run()`'un KENDI hata yollari zaten temiz kalir, ama
    `_build_dependencies()` (orn. `load_account_context()` okumasi veya
    eksik bir secret) `orchestrator.run()`'a hic ULASMADAN basarisiz
    olabilir.
    """
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    session: Session = session_factory()
    try:
        dependencies = _build_dependencies(
            account_id, session, config_dir, reports_dir, secrets_file
        )
        result = run_account(account_id, dependencies, datetime.now(UTC), _LOCK_DURATION)
    except RunAlreadyInProgressError as exc:
        session.rollback()
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        session.rollback()
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()

    return _report_run_result(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="linkedinbot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser(
        "seed", help="V1'in tek hesabini ve ilk config profilini olusturur (Roadmap M1.4)."
    )
    seed_parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("config"),
        help="system.defaults.yaml ve accounts/ alt dizinini iceren dizin (varsayilan: ./config).",
    )

    config_parser = subparsers.add_parser("config", help="Config ile ilgili komutlar.")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    validate_parser = config_subparsers.add_parser(
        "validate",
        help=(
            "Bir config dosya ciftini (system.defaults.yaml + "
            "accounts/default.account.yaml) semaya ve is kurallarina karsi "
            "dogrular (Roadmap M2.4)."
        ),
    )
    validate_parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("config"),
        help="system.defaults.yaml ve accounts/ alt dizinini iceren dizin (varsayilan: ./config).",
    )

    run_parser = subparsers.add_parser(
        "run",
        help=(
            "Bir hesap icin manuel bir calistirmayi hemen tetikler, otomatik "
            "cizelgeden bagimsiz olarak (Roadmap M9.7, FR-12)."
        ),
    )
    run_parser.add_argument(
        "--account",
        type=UUID,
        required=True,
        dest="account_id",
        help="Calistirilacak hesabin account_id'si (zorunlu).",
    )
    run_parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("config"),
        help="Prompt sablonlarini iceren dizin (varsayilan: ./config).",
    )
    run_parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Uretilen raporlarin kalici olarak yazilacagi dizin (varsayilan: ./reports).",
    )
    run_parser.add_argument(
        "--secrets-file",
        type=Path,
        default=Path("secrets.json"),
        help="Sifreli secrets deposu dosyasi (varsayilan: ./secrets.json).",
    )

    args = parser.parse_args(argv)

    if args.command == "seed":
        _run_seed_command(args.config_dir)
        return 0
    if args.command == "config" and args.config_command == "validate":
        return _run_config_validate_command(args.config_dir)
    if args.command == "run":
        return _run_run_command(
            args.account_id, args.config_dir, args.reports_dir, args.secrets_file
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
