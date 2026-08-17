"""main.py - surec giris noktasi (scheduler dongusu) (Roadmap M10.1, TDD Section 5/9).

TDD Section 9: "V1'de tek bir uzun omurlu Python sureci calisir (main.py)".
Bu modul, `SchedulerPort`/`APSchedulerAdapter`'i (M9.6) ve `bootstrap.py`
uzerinden Orchestrator'i (M9.3) birbirine baglayan composition root'tur -
`cli.py` gibi (M9.7), hicbir yeni is mantigi ICERMEZ, `bootstrap.py`'nin
disinda ikinci bir bagimlilik-kurma mimarisi ICAT ETMEZ.

**Iki AYRI DB oturumu, iki AYRI omur:**
1. `_on_trigger`'in actigi oturum: her calistirma icin TAZE acilir/kapanir
   (`cli.py::_run_run_command` ile AYNI desen) - `orchestrator.run()` KENDI
   transaction sinirini yonetir (bkz. bootstrap.py/orchestrator.py), bu
   yuzden burada basari yolunda ayri bir commit YOKTUR; hata yolunda
   savunma amacli bir rollback vardir.
2. `run_forever`'in actigi, GUNLER boyunca acik kalan "scheduler_session":
   YALNIZCA `APSchedulerAdapter`'in `account_repository`'sine (next_run_at
   kayitlari) aittir - `_on_trigger`'in oturumuyla PAYLASILMAZ (SQLAlchemy
   `Session` nesneleri thread-safe degildir; `_fire()` APScheduler'in
   KENDI worker thread'inde calisir - bkz. apscheduler_adapter.py modul
   dokumani). Bu oturumun motoru `pool_pre_ping=True` ile acilir (Roadmap
   M10.1 duzeltmesi, bkz. db/engine.py modul dokumani) - araya giren bir
   DB baglanti kopmasinin, sureç yeniden baslatilana kadar zamanlamayi
   sessizce durdurmasini onlemek icin.

**Commit siniri (bagimsiz incelemede bulunan bir bulgunun duzeltmesi,
kullanicidan acikca onaylandi - AUTOCOMMIT ONERISI GERI CEKILDI):**
`SqlAlchemyAccountRepository.update()` YALNIZCA `flush()` yapar, ASLA
`commit()` etmez (repository flush eder, cagiran commit eder - kod
tabaninin her yerinde tutarli kural). `run_forever`'in KENDISI, bu
oturumun TEK commit/rollback sinirini ACIKCA yonetir:
- `schedule_next_run()`'in ilk (surec baslangicindaki) cagrisindan HEMEN
  SONRA commit edilir - bu dogrudan/senkron cagri icin HICBIR APScheduler
  olayi ATESLENMEZ (dogrulandi: yalnizca `_fire()`'in KENDI kuyruklamasi
  APScheduler'in is dagitim/yeniden-kurma mekanizmasindan gecer).
- `EVENT_JOB_EXECUTED` (`_fire()`'in kendisi hata firlatmadan tamamlandigi
  an - `_fire()` `on_trigger`'in KENDI hatasini zaten yutup loglar, bu
  yuzden bu olay `_fire()`'in yeniden-kurma yazmasinin basarili oldugu
  anlamina gelir) -> `scheduler_session.commit()`.
- `EVENT_JOB_ERROR` (`_fire()`'in KENDISI - yeniden-kurma blogu, orn.
  `account_repository.get_by_id()/.update()` - hata firlattigi an) ->
  `scheduler_session.rollback()`.
Bu tasarim, `_on_trigger`'in KENDI basarisizliklarini (ayri oturumunda
yerel olarak rollback edilir - asagidaki `_make_on_trigger` dokumanina
bakiniz) ZATEN izole ettigi icin `EVENT_JOB_ERROR`'un `on_trigger`'dan
DEGIL yalnizca `_fire()`'in KENDI yeniden-kurma yazmasindan
tetiklenebilecegini varsayar - bu, gercek `APSchedulerAdapter._fire()`
kaynagi okunarak DOGRULANMIS bir davranistir.

**Test edilebilirlik:** `run_forever`, gercek bir `docker compose up`
soguk baslatmasini (M10.1'in kendi "Tamamlanma Dogrulamasi") otomatik
olarak taklit ETMEZ - bu kasitlidir (M10.2 zaten ayri, insan-yargili bir
dogrulama milestone'udur). Bunun yerine, `register_signal_handlers` (testler
sirasinda GERCEK `SIGINT`/`SIGTERM` islenmesini pytest surecinin KENDISine
karismasin diye kapatilabilir - `signal.signal()` yalnizca ana thread'de
calisir VE surec-genelinde bir yan etkidir) ve `shutdown_event` (bir arka
plan thread'i tarafindan tetiklenerek `wait()`'in sonsuza kadar
BLOKLANMASINI onler) parametreleri, alt parcalarin (`_resolve_account_id`,
`_load_schedule_settings`, `_make_on_trigger`, `_attach_commit_listeners`)
gercek bir `BackgroundScheduler` ile UCTAN UCA (ama gercek DB'ye
dokunmadan) dogrulanmasini saglar (bkz. tests/unit/test_main.py).
"""

from __future__ import annotations

import contextlib
import os
import signal
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from linkedinbot.adapters.scheduling.apscheduler_adapter import APSchedulerAdapter
from linkedinbot.bootstrap import LOCK_DURATION, build_dependencies, run_account
from linkedinbot.config.loader import load_account_context
from linkedinbot.db.engine import create_db_engine, create_session_factory
from linkedinbot.db.repositories.account_repository import SqlAlchemyAccountRepository
from linkedinbot.domain.run_log import RunStatus, TriggerType
from linkedinbot.ports.linkedin_port import LinkedInPort, SessionInvalidError

ACCOUNT_ID_ENV_VAR = "ACCOUNT_ID"
# M11.3 (Roadmap Faz 11, "Basarisizlik Gorunurlugu"): bildirim altyapisi
# (kuyruk/webhook/e-posta) INSA ETMEDEN, zaten bind-mount edilmis
# `reports/` dizinine (kullanicinin raporlari okumak icin ZATEN baktigi
# TEK yer) acikca adlandirilmis bir isaret dosyasi yazilir. `main.py`
# gercek dagitimda Docker/Linux konteyneri ICINDE calisir (bkz. Dockerfile
# CMD) - macOS'a ozgu bir bildirim mekanizmasi (orn. `osascript`) buradan
# DOGRUDAN tetiklenemez (konteynerde mevcut degildir, host'a da sizmaz);
# bu yuzden mekanizma, HER IKI tarafta da (container/host) calisan, zaten
# var olan bind-mount'a yazmaktir.
_SESSION_ALERT_FILE_NAME = "NEEDS_LOGIN.txt"


def _resolve_account_id(env: dict[str, str] | None = None) -> UUID:
    values = env if env is not None else os.environ
    raw_value = values.get(ACCOUNT_ID_ENV_VAR)
    if raw_value is None:
        raise ValueError(
            f"{ACCOUNT_ID_ENV_VAR} ortam degiskeni ayarlanmamis - main.py hangi "
            "hesabi calistiracagini bilemez (bkz. Roadmap M10.1)."
        )
    try:
        return UUID(raw_value)
    except ValueError as exc:
        raise ValueError(f"{ACCOUNT_ID_ENV_VAR} gecerli bir UUID degil: {raw_value!r}") from exc


def _load_schedule_settings(account_id: UUID, session: Session) -> tuple[timedelta, timedelta]:
    account_context = load_account_context(account_id, session)
    schedule = account_context.config_profile.schedule
    return timedelta(days=schedule.interval_days), timedelta(minutes=schedule.jitter_minutes)


def _session_alert_path(reports_dir: Path) -> Path:
    return reports_dir / _SESSION_ALERT_FILE_NAME


def _write_session_alert(reports_dir: Path, account_id: UUID) -> None:
    """M11.3: bir zamanlanmis calistirma basarisiz olup hesabin oturumu
    su an gecersiz oldugunda cagrilir (bkz. `_session_is_currently_invalid()`).
    Yazma HATASI (izin, disk dolu vb.) best-effort'tur ve SESSIZCE yutulur -
    cagiranin kendi hata isleme akisini MASKELEMEZ (StructuredLogger'in
    kendi "best-effort sozlesmesi" ile ayni ilke, bkz.
    logging/structured_logger.py modul dokumani)."""
    with contextlib.suppress(OSError):
        _session_alert_path(reports_dir).write_text(
            "LinkedIn oturumu gecersiz - zamanlanmis calistirmalar bu "
            f"hesap icin basarisiz oluyor (account_id: {account_id}).\n\n"
            "Duzeltmek icin interaktif giris akisini (ensure_session, "
            "Roadmap M3.1) HOST makinede yeniden calistirin.\n\n"
            f"Son basarisiz deneme: {datetime.now(UTC).isoformat()}\n",
            encoding="utf-8",
        )


def _clear_session_alert(reports_dir: Path) -> None:
    """M11.3: bir SONRAKI basarili zamanlanmis calistirma cagirir - boylece
    dosyanin VARLIGI her zaman "su an cozulmemis bir oturum sorunu var"
    anlamina gelir, eski/artik gecersiz bir uyari olarak KALICI KALMAZ.
    Dosya zaten yoksa (hic uyari yazilmamissa) sessizce hicbir sey yapmaz."""
    with contextlib.suppress(OSError):
        _session_alert_path(reports_dir).unlink(missing_ok=True)


def _session_is_currently_invalid(
    linkedin_port: LinkedInPort, account_id: UUID, session: Session
) -> bool:
    """M11.3 duzeltmesi (M12'de canli bir zamanlanmis calistirmaya karsi
    kesfedilen gercek bir kusur - bkz. Roadmap M12 doğrulama notu):
    `orchestrator.run()` (kendi "merkezi hata siniflandirma noktasi"
    yorumuna bakiniz) `RunAlreadyInProgressError` DISINDAKI HERHANGI bir
    istisnayi (`SessionInvalidError` DAHIL) yakalayip bir Failed RunLog
    yazar ve NORMAL DONER - hic firlatmaz. `bootstrap.run_account()`'un
    KENDI dokumanindaki "hicbir istisna yakalanmaz, oldugu gibi sizar"
    varsayimi, `SessionInvalidError` icin YANLIS - bu davranis KASITLI ve
    `cli._run_run_command`'in KENDI `_report_run_result()`'inin dayandigi,
    DEGISTIRILMEMESI gereken bir sozlesmedir (degistirilirse CLI'nin hata
    bicimlendirmesi bozulur).

    **Neden DB'nin `session_status` sutunu DOGRUDAN okunmaz (ilk taslagin
    kendi hatasi, canli bir entegrasyon testiyle YAKALANDI):**
    `SessionManager.validate()`, oturum gecersizse `session_status=EXPIRED`'i
    yalnizca `flush()` eder (COMMIT ETMEZ) ve sonra firlatir (bkz.
    session_manager.py). Bu istisna `_run_pipeline()`'in ta EN BASINDA
    (validate(), pipeline'in ilk adimidir) olustugu icin,
    `orchestrator.run()`'un KENDI `except Exception` dali bu flush'i
    `dependencies.session.rollback()` ile HENUZ commit edilmeden GERI ALIR
    - boylece `_on_trigger`'in kendi (AYRI) oturumundan `session_status`'u
    okumak, gercekte az once gecersizlesmis bir oturum icin bile YANLISLIKLA
    "valid" doner (kanit: tests/integration/db entegrasyon senaryosu ile
    dogrulandi). Bu yuzden burada, calistirma basarisiz olduktan SONRA
    `linkedin_port.validate()` BILEREK IKINCI KEZ cagrilir - taze, otoriter
    bir cevap alinir VE (istisna varsa) onun flush'i BU KEZ `_on_trigger`'in
    KENDI oturumunda dogrudan commit edilir (orchestrator.run()'un rollback'i
    ARTIK araya giremez), boylece DB de dogru sekilde EXPIRED yansitir."""
    try:
        linkedin_port.validate(account_id)
    except SessionInvalidError:
        session.commit()
        return True
    return False


def _make_on_trigger(
    config_dir: Path, reports_dir: Path, secrets_file: Path, profile_dir: Path
) -> Callable[[UUID], None]:
    """`APSchedulerAdapter`'a enjekte edilecek `on_trigger`'i uretir.

    Her cagri icin TAZE bir engine/session acar/kapatir (`cli.py`'nin
    `_run_run_command`'iyla AYNI desen) - `run_forever`'in KENDI, gunler
    boyunca acik kalan `scheduler_session`'iyla PAYLASILMAZ. Basari
    yolunda ayri bir commit YOKTUR (`orchestrator.run()` KENDI transaction
    sinirini yonetir); hata yolunda rollback edip yeniden firlatir -
    `_fire()` bu hatayi zaten yutup loglayacagi icin (bkz. modul dokumani)
    bu yalnizca bu oturumun kendi temizligi icindir.

    M11.3 (M12'de duzeltilen bir kusurdan sonra): `run_account()` HER ZAMAN
    normal doner (`orchestrator.run()` `RunAlreadyInProgressError` DISINDA
    hicbir istisna firlatmaz - bkz. `_session_is_currently_invalid()`'in
    kendi dokumani), bu yuzden alarm mantigi bir `except SessionInvalidError`
    dalina DEGIL, donen `RunLog.status`'a ve calistirma SONRASI `linkedin_port
    .validate()`'in BILEREK ikinci kez cagrilmasina dayanir (yine
    `_session_is_currently_invalid()`'in kendi dokumanina bakiniz - DB'nin
    `session_status` sutununu dogrudan okumak, orchestrator.run()'un kendi
    rollback'i yuzunden GUVENILMEZDIR). `except Exception` dali (rollback +
    reraise) yalnizca GERCEKTEN beklenmedik hatalar (orn.
    `build_dependencies()`'in kendisinin basarisiz olmasi) icindir - TUM
    diger istisna turleri icin DEGISMEDEN kalir.
    """

    def _on_trigger(account_id: UUID) -> None:
        engine = create_db_engine()
        session_factory = create_session_factory(engine)
        session: Session = session_factory()
        try:
            dependencies = build_dependencies(
                account_id, session, config_dir, reports_dir, secrets_file, profile_dir
            )
            result = run_account(
                account_id, dependencies, datetime.now(UTC), LOCK_DURATION, TriggerType.SCHEDULED
            )
            if result.status == RunStatus.FAILED and _session_is_currently_invalid(
                dependencies.linkedin_port, account_id, session
            ):
                _write_session_alert(reports_dir, account_id)
            else:
                _clear_session_alert(reports_dir)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            engine.dispose()

    return _on_trigger


def _attach_commit_listeners(scheduler: BackgroundScheduler, session: Session) -> None:
    """`scheduler_session`'in TEK commit/rollback sinirini kurar (bkz. modul
    dokumaninin "Commit siniri" bolumu). `APSchedulerAdapter(scheduler=...)`'a
    verilmeden ONCE cagrilmalidir."""

    def _on_job_executed(event: JobExecutionEvent) -> None:
        session.commit()

    def _on_job_error(event: JobExecutionEvent) -> None:
        session.rollback()

    scheduler.add_listener(_on_job_executed, EVENT_JOB_EXECUTED)
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)


def run_forever(
    account_id: UUID,
    config_dir: Path,
    reports_dir: Path,
    secrets_file: Path,
    profile_dir: Path,
    *,
    shutdown_event: threading.Event | None = None,
    register_signal_handlers: bool = True,
) -> None:
    startup_engine = create_db_engine()
    startup_session_factory = create_session_factory(startup_engine)
    startup_session: Session = startup_session_factory()
    try:
        interval, jitter_window = _load_schedule_settings(account_id, startup_session)
    finally:
        startup_session.close()
        startup_engine.dispose()

    scheduler_engine = create_db_engine(pool_pre_ping=True)
    scheduler_session_factory = create_session_factory(scheduler_engine)
    scheduler_session: Session = scheduler_session_factory()
    try:
        account_repository = SqlAlchemyAccountRepository(scheduler_session)

        raw_scheduler = BackgroundScheduler()
        _attach_commit_listeners(raw_scheduler, scheduler_session)

        on_trigger = _make_on_trigger(config_dir, reports_dir, secrets_file, profile_dir)
        scheduler = APSchedulerAdapter(
            account_repository=account_repository, on_trigger=on_trigger, scheduler=raw_scheduler
        )
        try:
            scheduler.schedule_next_run(account_id, interval, jitter_window)
            scheduler_session.commit()

            event = shutdown_event if shutdown_event is not None else threading.Event()
            if register_signal_handlers:
                signal.signal(signal.SIGTERM, lambda signum, frame: event.set())
                signal.signal(signal.SIGINT, lambda signum, frame: event.set())

            event.wait()
        finally:
            scheduler.shutdown()
    finally:
        scheduler_session.close()
        scheduler_engine.dispose()


def main() -> None:
    account_id = _resolve_account_id()
    config_dir = Path(os.environ.get("CONFIG_DIR", "config"))
    reports_dir = Path(os.environ.get("REPORTS_DIR", "reports"))
    secrets_file = Path(os.environ.get("SECRETS_FILE", "secrets.json"))
    profile_dir = Path(os.environ.get("BROWSER_PROFILE_DIR", "browser-profile"))
    run_forever(account_id, config_dir, reports_dir, secrets_file, profile_dir)


if __name__ == "__main__":
    main()
