"""main.py icin birim testleri (Roadmap M10.1, TDD Section 5/9).

`run_forever`'in gercek bir `docker compose up` soguk baslatmasini
(M10.1'in kendi "Tamamlanma Dogrulamasi") burada TASLAMAK KASITLI OLARAK
YAPILMAZ - bu, ayri, insan-yargili bir dogrulama adimidir (M10.2). Bunun
yerine: (a) DB'ye dokunan `create_db_engine`/`create_session_factory`
sahtelerle degistirilir, (b) GERCEK bir `BackgroundScheduler` KISA
araliklarla (`test_apscheduler_adapter.py` ile AYNI desen) kullanilir, (c)
`register_signal_handlers=False` gercek `SIGINT`/`SIGTERM` islemeyi
pytest surecinin KENDISine karistirmaz, (d) `shutdown_event`, ilk
`on_trigger` cagrisi gozlemlendikten SONRA bir arka plan thread'i
tarafindan tetiklenerek `run_forever`'in sonsuza kadar bloklanmasini
onler.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from linkedinbot import main
from linkedinbot.domain.account import Account
from linkedinbot.domain.run_log import RunLog, RunStatus, TriggerType
from linkedinbot.ports.account_repository_port import AccountRepositoryPort
from linkedinbot.ports.linkedin_port import SessionInvalidError


def _wait_until(predicate, timeout: float = 3.0, poll_interval: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(poll_interval)
    return False


class _FakeEngine:
    def __init__(self, pool_pre_ping: bool) -> None:
        self.pool_pre_ping = pool_pre_ping
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class _FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def close(self) -> None:
        self.closed = True


class _FakeAccountRepository(AccountRepositoryPort):
    """`test_apscheduler_adapter.py`'nin KENDI `_FakeAccountRepository`'siyle
    AYNI desen (bu dosyaya ozel, kucultulmus bir kopyasi - "her test dosyasi
    kendi sahtelerini tanimlar" konvansiyonu). `run_forever`'in `_FakeSession`
    ile (SQLAlchemy `Session` arayuzunu UYGULAMAYAN, yalnizca commit/rollback/
    close cagrilarini SAYAN bir sahte) beraber calisabilmesi icin gercek
    `SqlAlchemyAccountRepository`'nin yerine gecer - `main.SqlAlchemyAccountRepository`
    monkeypatch edilerek enjekte edilir.
    """

    def __init__(self, session) -> None:  # noqa: ARG002 - Port imzasiyla uyum icin
        self._accounts: dict[UUID, Account] = {}

    def seed(self, account: Account) -> None:
        self._accounts[account.account_id] = account

    def create(self, account: Account) -> Account:
        raise NotImplementedError("Bu test dosyasinda kullanilmiyor.")

    def get_by_id(self, account_id: UUID) -> Account | None:
        return self._accounts.get(account_id)

    def update(self, account: Account) -> Account:
        self._accounts[account.account_id] = account
        return account


def _patch_db(monkeypatch) -> tuple[list[_FakeEngine], list[_FakeSession]]:
    engines: list[_FakeEngine] = []
    sessions: list[_FakeSession] = []

    def fake_create_db_engine(database_url: str | None = None, pool_pre_ping: bool = False):
        engine = _FakeEngine(pool_pre_ping)
        engines.append(engine)
        return engine

    def fake_create_session_factory(engine):
        def factory():
            session = _FakeSession()
            sessions.append(session)
            return session

        return factory

    monkeypatch.setattr(main, "create_db_engine", fake_create_db_engine)
    monkeypatch.setattr(main, "create_session_factory", fake_create_session_factory)
    return engines, sessions


# ---------------------------------------------------------------------------
# _resolve_account_id
# ---------------------------------------------------------------------------


def test_resolve_account_id_returns_the_uuid_when_present():
    account_id = uuid4()

    assert main._resolve_account_id({"ACCOUNT_ID": str(account_id)}) == account_id


def test_resolve_account_id_raises_value_error_when_missing():
    with pytest.raises(ValueError, match="ACCOUNT_ID"):
        main._resolve_account_id({})


def test_resolve_account_id_raises_value_error_when_not_a_valid_uuid():
    with pytest.raises(ValueError, match="ACCOUNT_ID"):
        main._resolve_account_id({"ACCOUNT_ID": "not-a-uuid"})


# ---------------------------------------------------------------------------
# _make_on_trigger
# ---------------------------------------------------------------------------


class _FakeLinkedInPort:
    """`_session_is_currently_invalid()`, Failed bir calistirmadan SONRA
    `linkedin_port.validate()`'i BILEREK ikinci kez cagirir (bkz.
    `main._session_is_currently_invalid()`'in kendi dokumani - DB'nin
    `session_status` sutununu dogrudan okumanin, `orchestrator.run()`'un
    KENDI rollback'i yuzunden GUVENILMEZ oldugu canli bir entegrasyon
    testiyle KANITLANMASINDAN SONRAKI tasarim). Bu sahte, o ikinci
    cagrinin basarili mi yoksa `SessionInvalidError` mi firlatacagini
    test basina yapilandirir."""

    def __init__(self, validate_error: Exception | None = None) -> None:
        self._validate_error = validate_error
        self.validate_calls: list[UUID] = []

    def validate(self, account_id: UUID) -> None:
        self.validate_calls.append(account_id)
        if self._validate_error is not None:
            raise self._validate_error


class _FakeDependencies:
    def __init__(self, linkedin_port: _FakeLinkedInPort) -> None:
        self.linkedin_port = linkedin_port


def _run_log(*, account_id: UUID, status: RunStatus, error_detail: str | None = None) -> RunLog:
    return RunLog(
        run_id=uuid4(),
        account_id=account_id,
        trigger_type=TriggerType.SCHEDULED,
        started_at=datetime.now(UTC),
        status=status,
        error_detail=error_detail,
    )


def test_make_on_trigger_passes_the_scheduled_trigger_type_and_cleans_up(monkeypatch):
    engines, sessions = _patch_db(monkeypatch)
    calls: list[tuple[UUID, TriggerType]] = []

    def _fake_build_dependencies(account_id, session, config_dir, reports_dir, secrets_file):
        return "deps"

    def _fake_run_account(account_id, dependencies, now, lock_duration, trigger_type):
        calls.append((account_id, trigger_type))
        return _run_log(account_id=account_id, status=RunStatus.SUCCESS)

    monkeypatch.setattr(main, "build_dependencies", _fake_build_dependencies)
    monkeypatch.setattr(main, "run_account", _fake_run_account)

    on_trigger = main._make_on_trigger(Path("config"), Path("reports"), Path("secrets.json"))
    account_id = uuid4()

    on_trigger(account_id)

    assert calls == [(account_id, TriggerType.SCHEDULED)]
    assert len(sessions) == 1
    assert sessions[0].rollback_count == 0
    assert sessions[0].closed is True
    assert engines[0].disposed is True


def test_make_on_trigger_rolls_back_and_still_cleans_up_on_failure(monkeypatch, tmp_path):
    # Bu, `run_account()`'un kendisinin cagrilamadigi (build_dependencies'in
    # KENDISI basarisiz oldugu) GERCEKTEN beklenmedik bir hata senaryosudur -
    # `except Exception` dali (rollback + reraise) hala BUNUN icindir,
    # M12'de duzeltilen sorundan ETKILENMEZ.
    engines, sessions = _patch_db(monkeypatch)

    def _raise(*args, **kwargs):
        raise RuntimeError("build_dependencies basarisiz oldu")

    monkeypatch.setattr(main, "build_dependencies", _raise)
    monkeypatch.setattr(main, "run_account", lambda *args, **kwargs: None)

    on_trigger = main._make_on_trigger(Path("config"), tmp_path, Path("secrets.json"))

    with pytest.raises(RuntimeError, match="build_dependencies basarisiz oldu"):
        on_trigger(uuid4())

    assert len(sessions) == 1
    assert sessions[0].rollback_count == 1
    assert sessions[0].closed is True
    assert engines[0].disposed is True
    assert not (tmp_path / "NEEDS_LOGIN.txt").exists()


def test_make_on_trigger_writes_a_session_alert_when_revalidation_confirms_session_invalid(
    monkeypatch, tmp_path
):
    # M12 duzeltmesi: `run_account()` (gercekte, `orchestrator.run()`
    # araciligiyla) `SessionInvalidError` firlatmaz - Failed bir RunLog
    # DONER. Alarm mantigi bunun uzerine, VE `linkedin_port.validate()`'in
    # calistirma SONRASI BILEREK ikinci kez cagrilmasinin sonucuna kurulur
    # (bkz. `main._session_is_currently_invalid()` - DB'nin `session_status`
    # sutununu dogrudan okumak, `orchestrator.run()`'un KENDI rollback'i
    # yuzunden GUVENILMEZ bulundu, bkz. o fonksiyonun kendi dokumani).
    account_id = uuid4()
    engines, sessions = _patch_db(monkeypatch)
    fake_port = _FakeLinkedInPort(validate_error=SessionInvalidError("oturum gecersiz"))

    def _fake_build_dependencies(account_id, session, config_dir, reports_dir, secrets_file):
        return _FakeDependencies(fake_port)

    def _fake_run_account(*args, **kwargs):
        return _run_log(
            account_id=account_id, status=RunStatus.FAILED, error_detail="oturum gecersiz"
        )

    monkeypatch.setattr(main, "build_dependencies", _fake_build_dependencies)
    monkeypatch.setattr(main, "run_account", _fake_run_account)

    on_trigger = main._make_on_trigger(Path("config"), tmp_path, Path("secrets.json"))

    on_trigger(account_id)  # artik hicbir sey FIRLATMAZ - Failed durum normal donustur

    alert_path = tmp_path / "NEEDS_LOGIN.txt"
    assert alert_path.exists()
    content = alert_path.read_text(encoding="utf-8")
    assert str(account_id) in content
    assert fake_port.validate_calls == [account_id]
    # `_session_is_currently_invalid()`, ikinci `validate()` cagrisinin
    # flush'ini KENDI oturumunda dogrudan commit eder (bkz. o fonksiyonun
    # dokumani) - `orchestrator.run()`'un rollback'i buraya ARTIK erisemez.
    assert len(sessions) == 1
    assert sessions[0].commit_count == 1
    assert sessions[0].rollback_count == 0
    assert sessions[0].closed is True
    assert engines[0].disposed is True


def test_make_on_trigger_does_not_write_a_session_alert_when_failure_is_not_session_related(
    monkeypatch, tmp_path
):
    # M11.3'un ozgullugu: Failed bir calistirma, oturum GECERLIYSE (orn.
    # gecici bir ag hatasi retry'lari tuketti) alarm YAZMAMALIDIR - yalnizca
    # HUMAN mudahalesi (yeniden giris) gerektiren durumlar icindir. Burada
    # ikinci `validate()` cagrisi BASARILI olur (SessionInvalidError firlatmaz).
    account_id = uuid4()
    _, sessions = _patch_db(monkeypatch)
    fake_port = _FakeLinkedInPort(validate_error=None)

    def _fake_build_dependencies(account_id, session, config_dir, reports_dir, secrets_file):
        return _FakeDependencies(fake_port)

    def _fake_run_account(*args, **kwargs):
        return _run_log(
            account_id=account_id,
            status=RunStatus.FAILED,
            error_detail="devre kesici tetiklendi",
        )

    monkeypatch.setattr(main, "build_dependencies", _fake_build_dependencies)
    monkeypatch.setattr(main, "run_account", _fake_run_account)

    on_trigger = main._make_on_trigger(Path("config"), tmp_path, Path("secrets.json"))
    on_trigger(account_id)

    assert not (tmp_path / "NEEDS_LOGIN.txt").exists()
    assert fake_port.validate_calls == [account_id]
    # Ikinci `validate()` basarili oldugu icin ek bir commit YOKTUR.
    assert sessions[0].commit_count == 0


def test_make_on_trigger_clears_a_previously_written_session_alert_on_success(
    monkeypatch, tmp_path
):
    # M11.3: onceki bir basarisiz calistirmadan kalma bir uyari dosyasi,
    # bir SONRAKI basarili calistirmada temizlenir - boylece dosyanin
    # VARLIGI her zaman "su an cozulmemis" anlamina gelir.
    (tmp_path / "NEEDS_LOGIN.txt").write_text("eski uyari", encoding="utf-8")
    account_id = uuid4()
    _patch_db(monkeypatch)

    def _fake_build_dependencies(account_id, session, config_dir, reports_dir, secrets_file):
        return "deps"

    def _fake_run_account(*args, **kwargs):
        return _run_log(account_id=account_id, status=RunStatus.SUCCESS)

    monkeypatch.setattr(main, "build_dependencies", _fake_build_dependencies)
    monkeypatch.setattr(main, "run_account", _fake_run_account)

    on_trigger = main._make_on_trigger(Path("config"), tmp_path, Path("secrets.json"))

    on_trigger(account_id)

    assert not (tmp_path / "NEEDS_LOGIN.txt").exists()


def test_make_on_trigger_does_not_raise_when_alert_write_fails_after_a_failed_run(
    monkeypatch, tmp_path
):
    # M11.3: `_write_session_alert()`'in kendi "best-effort, cagiranin
    # akisini MASKELEMEZ" garantisini dogrular - yazma HATASI (burada:
    # `reports_dir`'in mevcut olmayan bir alt-dizini) `_on_trigger`'in
    # KENDISININ beklenmedik bir sekilde FIRLATMASINA neden OLMAMALIDIR
    # (M12 duzeltmesinden SONRA, Failed bir calistirma zaten normal
    # DONER - firlatilacak orijinal bir istisna YOKTUR, bu yuzden burada
    # dogrulanan sey NORMAL TAMAMLANMADIR, bir onceki istisna-maskeleme
    # senaryosu DEGIL).
    account_id = uuid4()
    unwritable_reports_dir = tmp_path / "does-not-exist"
    engines, sessions = _patch_db(monkeypatch)
    fake_port = _FakeLinkedInPort(validate_error=SessionInvalidError("oturum gecersiz"))

    def _fake_build_dependencies(account_id, session, config_dir, reports_dir, secrets_file):
        return _FakeDependencies(fake_port)

    def _fake_run_account(*args, **kwargs):
        return _run_log(
            account_id=account_id, status=RunStatus.FAILED, error_detail="oturum gecersiz"
        )

    monkeypatch.setattr(main, "build_dependencies", _fake_build_dependencies)
    monkeypatch.setattr(main, "run_account", _fake_run_account)

    on_trigger = main._make_on_trigger(Path("config"), unwritable_reports_dir, Path("secrets.json"))

    on_trigger(account_id)  # firlatmamali

    assert len(sessions) == 1
    assert sessions[0].commit_count == 1
    assert sessions[0].rollback_count == 0
    assert sessions[0].closed is True
    assert engines[0].disposed is True


# ---------------------------------------------------------------------------
# _attach_commit_listeners
# ---------------------------------------------------------------------------


def test_attach_commit_listeners_commits_the_session_after_a_successful_job():
    session = _FakeSession()
    scheduler = BackgroundScheduler()
    main._attach_commit_listeners(scheduler, session)
    scheduler.start()
    try:
        scheduler.add_job(lambda: None, "date", run_date=datetime.now(UTC))

        assert _wait_until(lambda: session.commit_count == 1)
        assert session.rollback_count == 0
    finally:
        scheduler.shutdown(wait=False)


def test_attach_commit_listeners_rolls_back_the_session_after_a_raising_job():
    session = _FakeSession()
    scheduler = BackgroundScheduler()
    main._attach_commit_listeners(scheduler, session)
    scheduler.start()

    def _raising_job() -> None:
        raise RuntimeError("is basarisiz oldu")

    try:
        scheduler.add_job(_raising_job, "date", run_date=datetime.now(UTC))

        assert _wait_until(lambda: session.rollback_count == 1)
        assert session.commit_count == 0
    finally:
        scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# run_forever - tam kablolama (dogrulanmis M10.1 tasarimi)
# ---------------------------------------------------------------------------


def test_run_forever_commits_after_initial_schedule_and_after_each_execution(monkeypatch):
    engines, sessions = _patch_db(monkeypatch)
    monkeypatch.setattr(
        main,
        "_load_schedule_settings",
        lambda account_id, session: (timedelta(seconds=0.1), timedelta(seconds=0.02)),
    )
    on_trigger_calls: list[tuple[UUID, TriggerType]] = []
    monkeypatch.setattr(main, "build_dependencies", lambda *args, **kwargs: "deps")

    def _fake_run_account(account_id, dependencies, now, lock_duration, trigger_type):
        on_trigger_calls.append((account_id, trigger_type))
        return _run_log(account_id=account_id, status=RunStatus.SUCCESS)

    monkeypatch.setattr(main, "run_account", _fake_run_account)

    account_id = uuid4()

    def _fake_account_repository(session):
        repo = _FakeAccountRepository(session)
        repo.seed(
            Account(
                account_id=account_id,
                display_name="Test Hesabi",
                created_at=datetime.now(UTC),
                status="active",
                next_run_at=None,
            )
        )
        return repo

    monkeypatch.setattr(main, "SqlAlchemyAccountRepository", _fake_account_repository)

    shutdown_event = threading.Event()

    def _stop_after_first_fire() -> None:
        _wait_until(lambda: len(on_trigger_calls) >= 1, timeout=5.0)
        shutdown_event.set()

    stopper = threading.Thread(target=_stop_after_first_fire)
    stopper.start()
    try:
        main.run_forever(
            account_id,
            Path("config"),
            Path("reports"),
            Path("secrets.json"),
            shutdown_event=shutdown_event,
            register_signal_handlers=False,
        )
    finally:
        stopper.join(timeout=5.0)

    assert on_trigger_calls
    assert all(
        trigger_type == TriggerType.SCHEDULED for _account_id, trigger_type in on_trigger_calls
    )

    # engines[0]/sessions[0]: kisa-omurlu baslangic okuma oturumu.
    assert engines[0].pool_pre_ping is False
    assert sessions[0].commit_count == 0
    assert sessions[0].closed is True

    # engines[1]/sessions[1]: uzun-omurlu scheduler_session - pool_pre_ping=True
    # ile acilir, ilk schedule_next_run() sonrasi VE her basarili _fire()
    # sonrasi (EVENT_JOB_EXECUTED) commit edilir.
    assert engines[1].pool_pre_ping is True
    assert sessions[1].commit_count >= 2
    assert sessions[1].rollback_count == 0
    assert sessions[1].closed is True

    # on_trigger'in KENDI, her atesleme icin TAZE actigi oturum(lar).
    assert len(sessions) >= 3
    assert sessions[2].closed is True


# ---------------------------------------------------------------------------
# main() - ortam degiskeni kablolamasi
# ---------------------------------------------------------------------------


def test_main_reads_account_id_and_path_env_vars_and_delegates_to_run_forever(monkeypatch):
    account_id = uuid4()
    monkeypatch.setenv("ACCOUNT_ID", str(account_id))
    monkeypatch.setenv("CONFIG_DIR", "custom-config")
    monkeypatch.setenv("REPORTS_DIR", "custom-reports")
    monkeypatch.setenv("SECRETS_FILE", "custom-secrets.json")

    calls = []
    monkeypatch.setattr(main, "run_forever", lambda *args, **kwargs: calls.append(args))

    main.main()

    assert calls == [
        (
            account_id,
            Path("custom-config"),
            Path("custom-reports"),
            Path("custom-secrets.json"),
        )
    ]


def test_main_uses_default_paths_when_env_vars_are_unset(monkeypatch):
    account_id = uuid4()
    monkeypatch.setenv("ACCOUNT_ID", str(account_id))
    monkeypatch.delenv("CONFIG_DIR", raising=False)
    monkeypatch.delenv("REPORTS_DIR", raising=False)
    monkeypatch.delenv("SECRETS_FILE", raising=False)

    calls = []
    monkeypatch.setattr(main, "run_forever", lambda *args, **kwargs: calls.append(args))

    main.main()

    assert calls == [(account_id, Path("config"), Path("reports"), Path("secrets.json"))]
