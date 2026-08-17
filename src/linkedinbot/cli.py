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
kendi notu).

M10.1: Bagimlilik kurma mantigi (`build_dependencies()`/`run_account()`),
bagimsiz incelemede bulunan bir tasarim bulgusunun duzeltmesiyle
`bootstrap.py`'ye tasindi - `main.py`'nin bu dosyadan (`cli.py`) DOGRUDAN
import etmesi, TDD Section 5'in `main.py`/`cli.py`'yi BIRBIRINDEN
BAGIMSIZ giris noktalari olarak tanimlayan mimarisiyle celisen yanal
(sideways) bir bagimlilik yaratirdi (bkz. `bootstrap.py` modul dokumani).
Bu dosya artik YALNIZCA CLI sunumundan (argparse, cikis kodlari,
stdout/stderr) sorumludur.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import yaml
from sqlalchemy.orm import Session

from linkedinbot.adapters.linkedin.playwright_client import (
    LoginTimeoutError,
    perform_interactive_login,
)
from linkedinbot.adapters.linkedin.session_manager import mark_session_valid
from linkedinbot.bootstrap import LOCK_DURATION, build_dependencies, run_account
from linkedinbot.config.schema import AccountConfigProfile
from linkedinbot.config.validator import ConfigValidationError, validate_config
from linkedinbot.db.engine import create_db_engine, create_session_factory
from linkedinbot.db.models import AccountConfigProfileOrm
from linkedinbot.db.repositories.account_repository import SqlAlchemyAccountRepository
from linkedinbot.db.repositories.user_profile_repository import SqlAlchemyUserProfileRepository
from linkedinbot.domain.account import Account
from linkedinbot.domain.run_log import RunLog, RunStatus, TriggerType
from linkedinbot.domain.user_profile import Preferences, UserProfile
from linkedinbot.run.orchestrator import RunAlreadyInProgressError
from linkedinbot.run.run_lock import RunLock


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


def _run_run_command(
    account_id: UUID, config_dir: Path, reports_dir: Path, secrets_file: Path, profile_dir: Path
) -> int:
    """`linkedinbot run --account <id>`'in gercek CLI cagrisi (Roadmap M9.7).

    `orchestrator.run()` (dolayisiyla `run_account()`) KENDI transaction
    sinirini/commit'lerini yonetir (bkz. orchestrator.py modul dokumani,
    "eager cache, atomic final state") - bu yuzden burada basari yolunda
    AYRI bir `session.commit()` cagrisi YOKTUR (`seed()`'in aksine - o
    KENDI commit ETMEYEN bir fonksiyondur, transaction siniri cagirana
    birakilir). Hata yollarindaki `session.rollback()` savunma amaclidir:
    `orchestrator.run()`'un KENDI hata yollari zaten temiz kalir, ama
    `build_dependencies()` (orn. `load_account_context()` okumasi veya
    eksik bir secret) `orchestrator.run()`'a hic ULASMADAN basarisiz
    olabilir.

    `run_account()`'a `TriggerType.MANUAL` ACIKCA gecirilir (M10.1
    duzeltmesi: `bootstrap.py`'ye tasinirken `trigger_type` bir parametre
    haline geldi - `main.py`'nin `TriggerType.SCHEDULED` gecirecegi AYNI
    fonksiyon).
    """
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    session: Session = session_factory()
    try:
        dependencies = build_dependencies(
            account_id, session, config_dir, reports_dir, secrets_file, profile_dir
        )
        result = run_account(
            account_id, dependencies, datetime.now(UTC), LOCK_DURATION, TriggerType.MANUAL
        )
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


# ---------------------------------------------------------------------------
# `login` (Faz 13, persistent Chromium profili mimarisi). Onceki turlerde
# onaylanan tasarim: `docker compose exec app linkedinbot login --account
# <id>` ile, Commit 1'de hazirlanan Xvfb/x11vnc/noVNC altyapisini kullanarak,
# ZATEN CALISAN `app` konteyneri ICINDE calistirilmak uzere tasarlanmistir -
# ana surecin (main.py, APScheduler dongusu) PID 1 olarak calismaya devam
# etmesine hicbir sekilde dokunmaz (bkz. entrypoint.sh'in kendi dokumani).
# ---------------------------------------------------------------------------


def _run_login_command(account_id: UUID, profile_dir: Path) -> int:
    """`linkedinbot login --account <id>`'in gercek CLI cagrisi.

    `RunLock`'un KENDISI DEGISTIRILMEDEN, `orchestrator.run()`'un KENDI
    kullanim deseniyle (bkz. orchestrator.py) AYNI sekilde yeniden
    kullanilir - kendi `lock_owner`'i (`login-{uuid4()}`, ayirt edici
    bir onek ile) ve AYNI `bootstrap.LOCK_DURATION` (yeni bir sabit ICAT
    EDILMEZ) ile. Bu, bir scheduled/manuel pipeline calistirmasinin (KENDI
    RunLock kullanimi zaten var, orchestrator.py degismedi) bu login
    akisiyla AYNI hesabin kalici Chromium profilini ES ZAMANLI acmaya
    calismasini, Chromium'un kendi SingletonLock'undan ONCE, uygulama
    seviyesinde engeller (bkz. session_manager.py/playwright_client.py
    "Mimari degisiklik" notlari - ayni profili iki ayri Chromium process'inin
    ES ZAMANLI acmasi RunLock olmadan mumkun olurdu).

    Kilit alinamazsa (baska bir pipeline calistirmasi surerken) HICBIR
    tarayici/Xvfb kaynagi ACILMADAN acik bir mesajla (kullanicidan acikca
    istenen, sabit Ingilizce metin) 1 doner - "hicbir is denenmedi"
    senaryosu, `orchestrator.run()`'un KENDI RunLock-mesgul davranisiyla
    (RunAlreadyInProgressError) AYNI ilkeyi izler.

    Hesap dogrulamasi (`SqlAlchemyAccountRepository.get_by_id()`) `RunLock.
    acquire()`'dan ONCE yapilir - `orchestrator.run()`'un KENDI, `run_locks.
    account_id`'nin `accounts.account_id`'ye FK tasidigi icin ZORUNLU
    kildigi AYNI sirayla (bkz. orchestrator.py'nin kendi "Duzeltme notu") -
    var olmayan bir hesap icin `run_locks`'a HICBIR ZAMAN dokunulmaz.

    `mark_session_valid()` (session_manager.py) YALNIZCA `perform_interactive
    _login()` HICBIR istisna firlatmadan donerse cagrilir - basarisiz bir
    giris (`LoginTimeoutError` DAHIL) `linkedin_sessions`'a ASLA `VALID`
    yazmaz (bkz. asagidaki inner try/except'in `return 1` yolu). Bu cagri
    ikinci bir RunLock/SessionManager INSA ETMEZ - zaten acik olan `session`
    ve zaten tutulan kilit kapsami ICINDE calisir. Bu metodun sorumlulugu
    SADECE "interaktif giris basariyla tamamlandi, kalici profil hazir"
    bilgisini kaydetmektir - LinkedIn'in bu profili GERCEKTEN kabul edip
    etmedigini (canli kontrol) SORMAZ/İDDİA ETMEZ; bu, `SessionManager.
    validate()`'in (Session Validation, pipeline'in ilk adimi) AYRI
    sorumlulugudur (bkz. mark_session_valid()'in kendi dokumani).
    """
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    session: Session = session_factory()
    lock_owner = f"login-{uuid4()}"
    run_lock = RunLock(session)
    lock_acquired = False
    try:
        account = SqlAlchemyAccountRepository(session).get_by_id(account_id)
        if account is None:
            print(f"Hesap bulunamadi: {account_id}", file=sys.stderr)
            return 1

        now = datetime.now(UTC)
        lock_acquired = run_lock.acquire(account_id, lock_owner, now, LOCK_DURATION)
        if not lock_acquired:
            print(
                "Account currently has an active pipeline run; login cannot start.",
                file=sys.stderr,
            )
            return 1
        session.commit()

        account_profile_dir = profile_dir / str(account_id)
        try:
            perform_interactive_login(account_profile_dir)
        except LoginTimeoutError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        # Faz 13 regresyon duzeltmesi (adversarial review'da bulunan blocker):
        # basarili interaktif giris SONRASI, `ensure_session()`'in KENDI
        # kullandigi AYNI DB-yazma yolu (`mark_session_valid()`, session_
        # manager.py) burada da cagrilir - aksi halde hic `linkedin_sessions`
        # satiri olmayan bir hesap icin (orn. ilk giris) `validate()`'in
        # "existing is None -> SessionInvalidError" guvenlik agi, GERCEKTEN
        # gecerli olan bu profili canli kontrol ETMEDEN reddederdi (M10.2'nin
        # duzelttigi kalici kilitlenme sinifinin farkli bir kod yolundan
        # geri gelmesi). Ikinci bir RunLock/SessionManager INSA EDILMEZ - bu
        # cagri, `_run_login_command()`'in KENDI (yukarida zaten alinmis)
        # RunLock kapsami ICINDE, AYNI `session` uzerinden yapilir.
        mark_session_valid(session, account_id)
    except Exception:
        session.rollback()
        raise
    finally:
        if lock_acquired:
            run_lock.release(account_id, lock_owner)
            session.commit()
        session.close()
        engine.dispose()

    print(f"Login basarili: account_id={account_id}, profile_dir={account_profile_dir}")
    return 0


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
    run_parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path("browser-profile"),
        help=(
            "Kalici Chromium profillerinin (hesap-bazli alt-dizinler) "
            "kok dizini (varsayilan: ./browser-profile)."
        ),
    )

    login_parser = subparsers.add_parser(
        "login",
        help=(
            "Bir hesap icin interaktif LinkedIn girisini tetikler; kalici "
            "Chromium profilini olusturur/gunceller (Faz 13)."
        ),
    )
    login_parser.add_argument(
        "--account",
        type=UUID,
        required=True,
        dest="account_id",
        help="Giris yapilacak hesabin account_id'si (zorunlu).",
    )
    login_parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path("browser-profile"),
        help=(
            "Kalici Chromium profillerinin (hesap-bazli alt-dizinler) "
            "kok dizini (varsayilan: ./browser-profile)."
        ),
    )

    args = parser.parse_args(argv)

    if args.command == "seed":
        _run_seed_command(args.config_dir)
        return 0
    if args.command == "config" and args.config_command == "validate":
        return _run_config_validate_command(args.config_dir)
    if args.command == "run":
        return _run_run_command(
            args.account_id, args.config_dir, args.reports_dir, args.secrets_file, args.profile_dir
        )
    if args.command == "login":
        return _run_login_command(args.account_id, args.profile_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
