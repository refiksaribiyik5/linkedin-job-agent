"""APSchedulerAdapter icin birim testleri (Roadmap M9.6, TDD Section 12).

Bu dosya `AccountRepositoryPort`'un GERCEK (DB'ye dokunan) bir uygulamasini
DEGIL, bellek-ici bir sahteyi kullanir (bu projenin `_FakeLinkedInPort`/
`_ScriptedLLMGateway` deseniyle AYNI yaklasim) - `SqlAlchemyAccountRepository`
zaten kendi entegrasyon testlerinde (M1.3) dogrulanmistir; burada test edilen
SADECE `APSchedulerAdapter`'in KENDI mantigidir (next_run_at cozumleme,
jitter, yeniden-kurma, iptal).

Zamanlama testlerinin bir kismi (fiilen tetiklenme, yeniden-kurma) GERCEK
bir `BackgroundScheduler` ve KISA (saniyenin bir kismi) gercek araliklar
kullanir - Roadmap M9.6'nin kendi "Tamamlanma Dogrulamasi" metninin ("Kisa
araligli manuel test") otomatik karsiligi. `misfire_grace_time` bilerek
DOKUNULMAMIS APScheduler varsayilaninda (1 saniye) birakildigi icin, test
araliklari bu esigin ALTINDA kalacak sekilde (saniyenin onda biri
mertebesinde) secilir - aksi halde testler kendi kendini "misfire" olarak
kacirip gercek bir hatayi degil, test zamanlamasini sinamis olurdu.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from linkedinbot.adapters.scheduling.apscheduler_adapter import APSchedulerAdapter
from linkedinbot.domain.account import Account
from linkedinbot.ports.account_repository_port import AccountRepositoryPort


class _FakeAccountRepository(AccountRepositoryPort):
    def __init__(self, accounts: dict[UUID, Account] | None = None) -> None:
        self._accounts = dict(accounts or {})
        self.update_calls: list[Account] = []

    def create(self, account: Account) -> Account:
        raise NotImplementedError("Bu test dosyasinda kullanilmiyor.")

    def get_by_id(self, account_id: UUID) -> Account | None:
        return self._accounts.get(account_id)

    def update(self, account: Account) -> Account:
        self._accounts[account.account_id] = account
        self.update_calls.append(account)
        return account


def _account(account_id: UUID, next_run_at: datetime | None = None) -> Account:
    return Account(
        account_id=account_id,
        display_name="Test Account",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        status="active",
        next_run_at=next_run_at,
    )


def _wait_until(predicate, timeout: float = 3.0, poll_interval: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(poll_interval)
    return False


@pytest.fixture
def repository() -> _FakeAccountRepository:
    return _FakeAccountRepository()


def test_schedule_next_run_computes_a_fresh_time_when_never_scheduled(repository):
    account_id = uuid4()
    repository.update(_account(account_id, next_run_at=None))
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    adapter = APSchedulerAdapter(
        account_repository=repository, on_trigger=lambda _: None, now=lambda: now
    )
    try:
        interval = timedelta(days=2)
        jitter_window = timedelta(minutes=30)

        result = adapter.schedule_next_run(account_id, interval, jitter_window)

        expected_center = now + interval
        assert expected_center - jitter_window <= result <= expected_center + jitter_window
        assert repository.get_by_id(account_id).next_run_at == result
    finally:
        adapter.shutdown()


def test_schedule_next_run_honors_an_existing_future_next_run_at_without_recomputing(repository):
    account_id = uuid4()
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    existing_next_run_at = now + timedelta(hours=5)
    repository.update(_account(account_id, next_run_at=existing_next_run_at))
    adapter = APSchedulerAdapter(
        account_repository=repository, on_trigger=lambda _: None, now=lambda: now
    )
    try:
        update_calls_before = len(repository.update_calls)

        result = adapter.schedule_next_run(account_id, timedelta(days=2), timedelta(minutes=30))

        assert result == existing_next_run_at
        # Zaten gelecekte gecerli bir deger vardi - GEREKSIZ bir yazma
        # (update()) YAPILMAMALIDIR (seed cagrisindan SONRAKI cagri sayisi).
        assert len(repository.update_calls) == update_calls_before
    finally:
        adapter.shutdown()


def test_schedule_next_run_recomputes_when_existing_next_run_at_is_in_the_past(repository):
    account_id = uuid4()
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    stale_next_run_at = now - timedelta(days=10)
    repository.update(_account(account_id, next_run_at=stale_next_run_at))
    adapter = APSchedulerAdapter(
        account_repository=repository, on_trigger=lambda _: None, now=lambda: now
    )
    try:
        interval = timedelta(days=2)
        jitter_window = timedelta(minutes=30)

        result = adapter.schedule_next_run(account_id, interval, jitter_window)

        # Gecmiste kalan bir deger asla oldugu gibi yeniden kullanilmaz -
        # "simdiden ileriye" taze bir deger hesaplanir (yeni bir "yakalama"
        # politikasi ICAT ETMEDEN - bkz. SchedulerPort modul dokumani).
        assert result != stale_next_run_at
        expected_center = now + interval
        assert expected_center - jitter_window <= result <= expected_center + jitter_window
        assert repository.get_by_id(account_id).next_run_at == result
    finally:
        adapter.shutdown()


def test_schedule_next_run_jitter_is_symmetric_and_bounded_across_many_trials(repository):
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    interval = timedelta(days=2)
    jitter_window = timedelta(minutes=30)
    adapter = APSchedulerAdapter(
        account_repository=repository, on_trigger=lambda _: None, now=lambda: now
    )
    try:
        deviations = []
        for _ in range(40):
            account_id = uuid4()
            repository.update(_account(account_id, next_run_at=None))
            result = adapter.schedule_next_run(account_id, interval, jitter_window)
            deviations.append((result - (now + interval)).total_seconds())

        assert all(
            -jitter_window.total_seconds() <= d <= jitter_window.total_seconds()
            for d in deviations
        )
        # Simetrik jitter: 40 denemede en azindan bir POZITIF ve bir
        # NEGATIF sapma gorulmelidir (yalnizca APScheduler'in kendi
        # tek-yonlu jitter'i - her zaman >= 0 - kullanilsaydi bu test
        # basarisiz olurdu).
        assert any(d > 0 for d in deviations)
        assert any(d < 0 for d in deviations)
    finally:
        adapter.shutdown()


def test_schedule_next_run_raises_for_unknown_account(repository):
    adapter = APSchedulerAdapter(
        account_repository=repository, on_trigger=lambda _: None, now=lambda: datetime.now(UTC)
    )
    try:
        with pytest.raises(ValueError, match="bulunamadi"):
            adapter.schedule_next_run(uuid4(), timedelta(days=2), timedelta(minutes=30))
    finally:
        adapter.shutdown()


def test_a_scheduled_trigger_fires_the_callback_within_the_jitter_window(repository):
    account_id = uuid4()
    repository.update(_account(account_id, next_run_at=None))
    triggered_with: list[UUID] = []
    adapter = APSchedulerAdapter(account_repository=repository, on_trigger=triggered_with.append)
    try:
        adapter.schedule_next_run(
            account_id, interval=timedelta(seconds=0.2), jitter_window=timedelta(seconds=0.05)
        )

        assert _wait_until(lambda: len(triggered_with) == 1, timeout=3.0)
        assert triggered_with == [account_id]
    finally:
        adapter.shutdown()


def test_after_firing_the_schedule_automatically_rearms_for_the_next_cycle(repository):
    account_id = uuid4()
    repository.update(_account(account_id, next_run_at=None))
    triggered_with: list[UUID] = []
    adapter = APSchedulerAdapter(account_repository=repository, on_trigger=triggered_with.append)
    try:
        adapter.schedule_next_run(
            account_id, interval=timedelta(seconds=0.2), jitter_window=timedelta(seconds=0.05)
        )

        assert _wait_until(lambda: len(triggered_with) == 1, timeout=3.0)
        first_next_run_at = repository.get_by_id(account_id).next_run_at
        assert first_next_run_at is not None

        assert _wait_until(lambda: len(triggered_with) == 2, timeout=3.0)
        assert triggered_with == [account_id, account_id]
        second_next_run_at = repository.get_by_id(account_id).next_run_at
        assert second_next_run_at is not None
        assert second_next_run_at != first_next_run_at
    finally:
        adapter.shutdown()


def test_a_raising_callback_does_not_prevent_rescheduling(repository):
    # Best-effort/izolasyon gereksinimi (M9.5'in ayni ilkesiyle tutarli):
    # on_trigger'in KENDI hatasi, zamanlamanin GERI KALANINI durdurmamalidir.
    account_id = uuid4()
    repository.update(_account(account_id, next_run_at=None))
    call_count = 0

    def _raising_on_trigger(triggered_account_id: UUID) -> None:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("simulated on_trigger failure")

    adapter = APSchedulerAdapter(account_repository=repository, on_trigger=_raising_on_trigger)
    try:
        adapter.schedule_next_run(
            account_id, interval=timedelta(seconds=0.2), jitter_window=timedelta(seconds=0.05)
        )

        assert _wait_until(lambda: call_count == 1, timeout=3.0)
        # Callback FIRLATTI, ama yeniden kurma YINE DE gerceklesmis olmalidir.
        assert _wait_until(lambda: call_count == 2, timeout=3.0)
        assert repository.get_by_id(account_id).next_run_at is not None
    finally:
        adapter.shutdown()


def test_restart_recovery_a_fresh_adapter_instance_honors_the_persisted_next_run_at(repository):
    account_id = uuid4()
    repository.update(_account(account_id, next_run_at=None))
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    first_adapter = APSchedulerAdapter(
        account_repository=repository, on_trigger=lambda _: None, now=lambda: now
    )
    try:
        first_result = first_adapter.schedule_next_run(
            account_id, timedelta(days=2), timedelta(minutes=30)
        )
    finally:
        first_adapter.shutdown()

    # "Surec yeniden baslatildi": TAMAMEN YENI bir adapter (yeni APScheduler
    # ornegi), AYNI (kalici) repository'ye karsi.
    second_adapter = APSchedulerAdapter(
        account_repository=repository,
        on_trigger=lambda _: None,
        now=lambda: now + timedelta(minutes=1),
    )
    try:
        second_result = second_adapter.schedule_next_run(
            account_id, timedelta(days=2), timedelta(minutes=30)
        )

        assert second_result == first_result
    finally:
        second_adapter.shutdown()


def test_cancel_removes_the_pending_job_and_clears_next_run_at(repository):
    account_id = uuid4()
    repository.update(_account(account_id, next_run_at=None))
    triggered_with: list[UUID] = []
    adapter = APSchedulerAdapter(account_repository=repository, on_trigger=triggered_with.append)
    try:
        adapter.schedule_next_run(
            account_id, interval=timedelta(seconds=0.2), jitter_window=timedelta(seconds=0.05)
        )

        adapter.cancel(account_id)

        assert repository.get_by_id(account_id).next_run_at is None
        # Iptal edilen bir tetikleme HICBIR ZAMAN ateslenmemelidir.
        time.sleep(0.4)
        assert triggered_with == []
    finally:
        adapter.shutdown()


def test_cancel_is_a_safe_no_op_when_nothing_is_scheduled(repository):
    account_id = uuid4()
    repository.update(_account(account_id, next_run_at=None))
    adapter = APSchedulerAdapter(
        account_repository=repository, on_trigger=lambda _: None, now=lambda: datetime.now(UTC)
    )
    try:
        adapter.cancel(account_id)  # firlatmamali
    finally:
        adapter.shutdown()


def test_cancel_racing_an_in_flight_fire_is_not_silently_undone():
    # Regression (independent review, gercek production bug): `cancel()`,
    # bir `_fire()` cagrisinin `on_trigger`'i HALA CALISIRKEN gelirse
    # (yeniden-kurma kuyrugu HENUZ baslamamisken), o `_fire()` cagrisi
    # `on_trigger` bittikten SONRA, cancel()'in `next_run_at=None`
    # yazdigindan HABERSIZ sekilde YENI bir next_run_at hesaplayip
    # SESSIZCE yeniden kuruluyor VE is_planned kaliyordu - `cancel()`
    # HICBIR HATA vermeden BASARISIZ oluyordu.
    account_id = uuid4()
    repository = _FakeAccountRepository({account_id: _account(account_id)})
    fired: list[UUID] = []
    on_trigger_entered = threading.Event()
    release_on_trigger = threading.Event()

    def _pausable_on_trigger(triggered_account_id: UUID) -> None:
        fired.append(triggered_account_id)
        on_trigger_entered.set()
        release_on_trigger.wait(timeout=5)

    adapter = APSchedulerAdapter(account_repository=repository, on_trigger=_pausable_on_trigger)
    try:
        adapter.schedule_next_run(
            account_id, interval=timedelta(seconds=0.05), jitter_window=timedelta(seconds=0.01)
        )

        # `on_trigger` baslayana kadar bekle - bu noktada `_fire()`'in
        # yeniden-kurma kuyrugu HENUZ CALISMAMISTIR (on_trigger donene
        # kadar baslamaz).
        assert _wait_until(lambda: on_trigger_entered.is_set(), timeout=3.0)
        assert len(fired) == 1

        # `on_trigger` HALA CALISIRKEN iptal et.
        adapter.cancel(account_id)
        assert repository.get_by_id(account_id).next_run_at is None

        # `on_trigger`'in donmesine izin ver - `_fire()`'in yeniden-kurma
        # kuyrugu ARTIK calisir; duzeltmeden SONRA, iptal edildigini
        # fark edip VAZGECMELIDIR.
        release_on_trigger.set()

        time.sleep(0.3)
        assert repository.get_by_id(account_id).next_run_at is None
        # Ve iptalden SONRA HICBIR yeni tetiklenme gerceklesmemelidir -
        # kisa bir sure daha bekleyip sayacin ARTMADIGINI dogrula.
        fired_count_after_cancel = len(fired)
        time.sleep(0.3)
        assert len(fired) == fired_count_after_cancel
    finally:
        adapter.shutdown()
