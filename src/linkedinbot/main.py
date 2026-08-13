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
from linkedinbot.domain.run_log import TriggerType

ACCOUNT_ID_ENV_VAR = "ACCOUNT_ID"


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


def _make_on_trigger(
    config_dir: Path, reports_dir: Path, secrets_file: Path
) -> Callable[[UUID], None]:
    """`APSchedulerAdapter`'a enjekte edilecek `on_trigger`'i uretir.

    Her cagri icin TAZE bir engine/session acar/kapatir (`cli.py`'nin
    `_run_run_command`'iyla AYNI desen) - `run_forever`'in KENDI, gunler
    boyunca acik kalan `scheduler_session`'iyla PAYLASILMAZ. Basari
    yolunda ayri bir commit YOKTUR (`orchestrator.run()` KENDI transaction
    sinirini yonetir); hata yolunda rollback edip yeniden firlatir -
    `_fire()` bu hatayi zaten yutup loglayacagi icin (bkz. modul dokumani)
    bu yalnizca bu oturumun kendi temizligi icindir.
    """

    def _on_trigger(account_id: UUID) -> None:
        engine = create_db_engine()
        session_factory = create_session_factory(engine)
        session: Session = session_factory()
        try:
            dependencies = build_dependencies(
                account_id, session, config_dir, reports_dir, secrets_file
            )
            run_account(
                account_id, dependencies, datetime.now(UTC), LOCK_DURATION, TriggerType.SCHEDULED
            )
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

        on_trigger = _make_on_trigger(config_dir, reports_dir, secrets_file)
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
    run_forever(account_id, config_dir, reports_dir, secrets_file)


if __name__ == "__main__":
    main()
