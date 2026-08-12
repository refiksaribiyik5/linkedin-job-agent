"""APSchedulerAdapter - `SchedulerPort`'un surec-ici APScheduler uygulamasi
(Roadmap M9.6, TDD Section 2/12).

**Bu adaptorun kapsami NE DEGILDIR:** `orchestrator.run()`'u cagirmaz,
`OrchestratorDependencies`'i somutlastirmaz. Tetiklenme aninda ne
yapilacagina (genellikle bir `orchestrator.run()` cagrisi) cagiran
(`on_trigger: Callable[[UUID], None]`, constructor'da enjekte edilir)
karar verir - bu, `main.py`'nin (TDD Section 5/9, henuz insa edilmemis)
sorumlulugudur (bkz. `ports/scheduler_port.py` modul dokumani, "sahiplik
siniri").

**Thread-safety notu (self-review bulgusu, gelecekteki entegratore
yonelik):** `_fire()` (dolayisiyla `on_trigger` VE `account_repository`
cagrilari), `BackgroundScheduler`'in KENDI executor thread'inde calisir -
cagiranin (main thread) thread'i DEGIL. `AccountRepositoryPort`'un GERCEK
(SQLAlchemy tabanli) bir uygulamasini bu adaptore enjekte edecek gelecekteki
`main.py`, o implementasyona ait `Session`'in bu adaptore OZEL/ayrilmis
oldugundan (CLI/ana akisla PAYLASILMADIGINDAN) emin olmalidir - SQLAlchemy
`Session` nesneleri thread-safe DEGILDIR. Bu adaptorun KENDISI hicbir
session-per-thread mekanizmasi UYGULAMAZ (boyle bir mekanizma DB katmaninin
sorumlulugudur, M9.6'nin kapsami DISINDADIR) - bu yalnizca gelecekteki
entegrasyon icin acikca belgelenen bir KISITTIR.

**Tasarim karari - "kendi kendini yeniden kuran tek-seferlik `DateTrigger`"
(APScheduler'in yerlesik `IntervalTrigger`si YERINE):** Iki AYRI gerekce
birlesir:

1. **Simetrik jitter:** NFR-14/TDD Section 12'nin formulu ACIKCA
   simetriktir: `next_run_at = last_run_at + interval_days ± random(
   jitter_window)` (PRD Section 14: "±30 dakika"). APScheduler'in KENDI
   `IntervalTrigger(jitter=N)` parametresi DOGRULANDI (kaynagi okunarak) -
   YALNIZCA TEK YONLUDUR: `next_fire_time += random.uniform(0, jitter)` -
   HER ZAMAN geciktirir, ASLA erkene almaz. Bu, NFR-14'un gereksinimiyle
   AYNI DEGILDIR.
2. **Kalici durumla tek-kaynak tutarlilik:** `accounts.next_run_at`
   (TDD v1.1 Fix 5), surec yeniden baslatildiginda geri yuklenecek TEK
   kalici referanstir. APScheduler'in kendi `next_run_time` durumu
   VARSAYILAN OLARAK yalnizca bellek-icidir (jobstore) ve tetiklenme
   ANINDA (is DAGITILIRKEN, tamamlanmasi BEKLENMEDEN - dogrulandi:
   `BaseScheduler._process_jobs`, `executor.submit_job()`'dan hemen
   sonra `job.trigger.get_next_fire_time()`'i cagirir) guncellenir. Bir
   yerlesik/tekrarlayan trigger kullanip cagirilan fonksiyonun ICINDEN
   APScheduler'in KENDI ic durumunu (`next_run_time`) okumaya calismak
   YARIS DURUMUNA (race) acik olurdu; AYRI bir hesaplama yapmak ise IKI
   BAGIMSIZ rastgele jitter cekilisine (biri APScheduler'in canli
   calistirdigi, digeri benim kalici olarak yazdigim) yol acip
   ikisinin ASLA TAM ORTUSMEMESINE neden olurdu. Bu yuzden `next_run_at`
   TEK BIR yerde (bu modulde) hesaplanir, kalici hale getirilir, ve HER
   dongu icin YENI bir tek-seferlik `DateTrigger` kaydedilir - "tek
   kaynak/tek hesaplama" ozelligini KORUR.

**Misfire davranisi (kullanici talimatiyla acikca sinirlandi - HICBIR
ozel "yakalama" (catch-up) mantigi EKLENMEZ):** `add_job()`'a
`misfire_grace_time` KASITLI OLARAK GECIRILMEZ - APScheduler'in kendi
varsayilani (1 saniye, kaynak okunarak dogrulandi:
`apscheduler.schedulers.base`'in `job_defaults`'i) OLDUGU GIBI kullanilir.
Somut sonucu: bir tetiklenme zamani BU esigi asarak gecikirse (orn. surec
uzun sure kapaliyken yeniden baslatilirsa VEYA bu 1 saniyelik pencere
ROUTINE bir sistem gecikmesiyle kacirilirsa), APScheduler bunu bir
`EVENT_JOB_MISSED` olarak LOGLAR ve ATLAR - `on_trigger` HICBIR ZAMAN
cagrilmaz. `DateTrigger` tek-seferlik oldugu icin (kaynak okunarak
dogrulandi: `get_next_fire_time()` bir kez `run_date`'i doner, SONRA
HER ZAMAN `None` doner), kacirilan bir tetikleme bu MODULUN yeniden-kurma
mantigini (`_fire()`'in KENDISI) TETIKLEMEZ - hesap, `schedule_next_run()`
tekrar cagirilana kadar (orn. bir SONRAKI surec yeniden baslatmasinda)
zamanlamadan DUSER. Bu, `misfire_grace_time`'i (orn. bu sistemin
gun-mertebesindeki periyoduna daha uygun bir degere) AYARLAMANIN veya
ozel bir "yeniden dene" mekanizmasi EKLEMENIN, PRD/TDD/Roadmap'in
HICBIRINDE tanimlanmayan bir is kurali ICAT ETMEK anlamina gelecegi
gerekcesiyle, KASITLI OLARAK yapilmamis bir tasarim kararidir.

**Kalicilik/yeniden-baslatma kurtarma:** `schedule_next_run()`, hesabin
ZATEN gelecekte bir `next_run_at`'i varsa bunu OLDUGU GIBI onurlandirir
(yeniden hesaplamaz) - bu, TDD Section 12 "Kalıcılık"in ("next_run_at
... surec yeniden baslatildiginda çizelge kaybolmaz") somut karsiligidir.
Bu metodun `main.py` (henuz insa edilmemis) tarafindan HER bilinen hesap
icin surec baslangicinda bir kez cagrilmasi BEKLENIR - bu adaptorun
KENDISI hicbir "tum hesaplari tara" davranisi UYGULAMAZ (M9.6'nin
"Oluşturulacak Dosyalar" listesi `main.py`'yi icermez).
"""

from __future__ import annotations

import contextlib
import logging
import random
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.date import DateTrigger

from linkedinbot.ports.account_repository_port import AccountRepositoryPort
from linkedinbot.ports.scheduler_port import SchedulerPort

logger = logging.getLogger(__name__)


def _job_id(account_id: UUID) -> str:
    return f"linkedinbot-scheduled-run-{account_id}"


class APSchedulerAdapter(SchedulerPort):
    def __init__(
        self,
        account_repository: AccountRepositoryPort,
        on_trigger: Callable[[UUID], None],
        scheduler: BaseScheduler | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._account_repository = account_repository
        self._on_trigger = on_trigger
        self._now = now
        self._scheduler = scheduler if scheduler is not None else BackgroundScheduler()
        if not self._scheduler.running:
            self._scheduler.start()
        # Cancellation-lifecycle duzeltmesi (independent review bulgusu,
        # gercek defect): `cancel()` ve `_fire()`'in yeniden-kurma kuyrugu,
        # AYNI hesap icin senkronize edilmemis bir oku-sonra-yaz calistirip
        # birbirini SESSIZCE UZERINE YAZABILIYORDU (biri cagiranin
        # thread'inde, digeri APScheduler'in worker thread'inde). Hesap
        # basina bir kilit, HER IKI metodun da AYNI hesap icin ASLA
        # es zamanli calismamasini garanti eder; `_cancelled_account_ids`
        # ise `_fire()`'in, on_trigger CALISIRKEN (kilit henuz alinmadan)
        # gelen bir cancel()'i de fark edip yeniden-kurmadan VAZGECMESINI
        # saglar (bkz. `_fire()`'in kendi yorumu).
        self._locks_guard = threading.Lock()
        self._locks: dict[UUID, threading.Lock] = {}
        self._cancelled_account_ids: set[UUID] = set()

    def _lock_for(self, account_id: UUID) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(account_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[account_id] = lock
            return lock

    def shutdown(self) -> None:
        """`BackgroundScheduler`'in kendi arka plan thread'ini durdurur.
        `SchedulerPort`'un soyut arayuzunun BIR PARCASI DEGILDIR (Roadmap'in
        `schedule_next_run`/`cancel` disinda bir islem tanimlamaz) - bu,
        yalnizca bu SOMUT adaptorun kaynak yasam dongusu icin gereken,
        testlerin (ve gelecekteki `main.py`'nin kapanis akisinin) cagirmasi
        gereken bir temizlik metodudur."""
        self._scheduler.shutdown(wait=False)

    def schedule_next_run(
        self, account_id: UUID, interval: timedelta, jitter_window: timedelta
    ) -> datetime:
        with self._lock_for(account_id):
            account = self._account_repository.get_by_id(account_id)
            if account is None:
                raise ValueError(f"Hesap bulunamadi: {account_id}")

            # Acikca yeniden zamanlamak, ONCEKI herhangi bir cancel()'i
            # gecersiz kilar (yeni bir zamanlama, tanimi geregi bir "iptal
            # edilmis" durumu SUPERSEDE eder).
            self._cancelled_account_ids.discard(account_id)

            now = self._now()
            if account.next_run_at is not None and account.next_run_at > now:
                next_run_at = account.next_run_at
            else:
                next_run_at = self._compute_next_run_at(now, interval, jitter_window)
                self._account_repository.update(
                    account.model_copy(update={"next_run_at": next_run_at})
                )

            self._scheduler.add_job(
                self._fire,
                trigger=DateTrigger(run_date=next_run_at),
                args=[account_id, interval, jitter_window],
                id=_job_id(account_id),
                replace_existing=True,
            )
            return next_run_at

    def cancel(self, account_id: UUID) -> None:
        with self._lock_for(account_id):
            # `_fire()`'in on_trigger'i HALA calisiyor olabilir (bu
            # noktada henuz kilit almaya calismamis olabilir) - bu
            # bayrak, o `_fire()` cagrisi daha SONRA yeniden-kurma
            # asamasina ulastiginda (kilit alindiginda) iptal edildigini
            # fark edip VAZGECMESINI saglar (bkz. `_fire()`).
            self._cancelled_account_ids.add(account_id)

            with contextlib.suppress(JobLookupError):
                # Zaten hicbir sey zamanlanmamis olabilir - sessiz no-op
                # (bkz. SchedulerPort.cancel()'in kendi dokumaninin ilkesi).
                self._scheduler.remove_job(_job_id(account_id))

            account = self._account_repository.get_by_id(account_id)
            if account is not None and account.next_run_at is not None:
                self._account_repository.update(account.model_copy(update={"next_run_at": None}))

    def _fire(self, account_id: UUID, interval: timedelta, jitter_window: timedelta) -> None:
        try:
            self._on_trigger(account_id)
        except Exception:
            # Izolasyon (M9.5'in "loglama is mantigina sizmaz" ilkesiyle
            # AYNI ruhta, burada TERSINE cevrilmis): on_trigger'in KENDI
            # hatasi zamanlamanin GERI KALANINI durdurmamalidir - asagidaki
            # yeniden-kurma HER KOSULDA (basari VEYA hata) calismalidir.
            logger.exception("on_trigger hesap %s icin basarisiz oldu", account_id)

        with self._lock_for(account_id):
            if account_id in self._cancelled_account_ids:
                # Bu tetiklenmenin on_trigger'i CALISIRKEN (veya bu blok
                # kilidi almayi BEKLERKEN) cancel() cagrildi - iptali
                # ONURLANDIR, yeniden kurma - cancel()'in etkisini
                # SESSIZCE UZERINE YAZMA (independent review bulgusu,
                # gercek defect - bkz. modul dokumani).
                self._cancelled_account_ids.discard(account_id)
                return

            next_run_at = self._compute_next_run_at(self._now(), interval, jitter_window)
            account = self._account_repository.get_by_id(account_id)
            if account is not None:
                self._account_repository.update(
                    account.model_copy(update={"next_run_at": next_run_at})
                )
            self._scheduler.add_job(
                self._fire,
                trigger=DateTrigger(run_date=next_run_at),
                args=[account_id, interval, jitter_window],
                id=_job_id(account_id),
                replace_existing=True,
            )

    @staticmethod
    def _compute_next_run_at(
        base: datetime, interval: timedelta, jitter_window: timedelta
    ) -> datetime:
        # NFR-14/TDD Section 12: "± random(jitter_window)" - SIMETRIK jitter
        # (bkz. modul dokumani) - `collection/collector.py::_apply_rate_limit`
        # ve `retry.py::_backoff_delay_ms` ile AYNI `random.uniform(-x, x)`
        # deseni.
        jitter_seconds = random.uniform(  # noqa: S311 - guvenlik/kriptografi disi, ayni gerekce
            -jitter_window.total_seconds(), jitter_window.total_seconds()
        )
        return base + interval + timedelta(seconds=jitter_seconds)
