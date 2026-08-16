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
from linkedinbot.domain.run_log import TriggerType
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


def test_make_on_trigger_passes_the_scheduled_trigger_type_and_cleans_up(monkeypatch):
    engines, sessions = _patch_db(monkeypatch)
    calls: list[tuple[UUID, TriggerType]] = []

    def _fake_build_dependencies(account_id, session, config_dir, reports_dir, secrets_file):
        return "deps"

    monkeypatch.setattr(main, "build_dependencies", _fake_build_dependencies)
    monkeypatch.setattr(
        main,
        "run_account",
        lambda account_id, dependencies, now, lock_duration, trigger_type: calls.append(
            (account_id, trigger_type)
        ),
    )

    on_trigger = main._make_on_trigger(Path("config"), Path("reports"), Path("secrets.json"))
    account_id = uuid4()

    on_trigger(account_id)

    assert calls == [(account_id, TriggerType.SCHEDULED)]
    assert len(sessions) == 1
    assert sessions[0].rollback_count == 0
    assert sessions[0].closed is True
    assert engines[0].disposed is True


def test_make_on_trigger_rolls_back_and_still_cleans_up_on_failure(monkeypatch, tmp_path):
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
    # M11.3: SessionInvalidError DISINDAKI bir hata icin uyari dosyasi
    # YAZILMAMALIDIR - yalnizca SessionInvalidError'a ozeldir.
    assert not (tmp_path / "NEEDS_LOGIN.txt").exists()


def test_make_on_trigger_writes_a_session_alert_on_session_invalid_error(monkeypatch, tmp_path):
    # Roadmap M11.3'un kendi "Tamamlanma Dogrulamasi": SessionInvalidError
    # firlatan sahte bir tetikleyici ile, yan etkinin (uyari dosyasi)
    # tam olarak bir kez tetiklendigi dogrulanir.
    engines, sessions = _patch_db(monkeypatch)

    def _fake_build_dependencies(account_id, session, config_dir, reports_dir, secrets_file):
        return "deps"

    def _raise_session_invalid(*args, **kwargs):
        raise SessionInvalidError("oturum gecersiz")

    monkeypatch.setattr(main, "build_dependencies", _fake_build_dependencies)
    monkeypatch.setattr(main, "run_account", _raise_session_invalid)

    on_trigger = main._make_on_trigger(Path("config"), tmp_path, Path("secrets.json"))
    account_id = uuid4()

    with pytest.raises(SessionInvalidError):
        on_trigger(account_id)

    alert_path = tmp_path / "NEEDS_LOGIN.txt"
    assert alert_path.exists()
    content = alert_path.read_text(encoding="utf-8")
    assert str(account_id) in content
    # Rollback/cleanup davranisi diger istisna turleriyle AYNI kalmalidir.
    assert len(sessions) == 1
    assert sessions[0].rollback_count == 1
    assert sessions[0].closed is True
    assert engines[0].disposed is True


def test_make_on_trigger_clears_a_previously_written_session_alert_on_success(
    monkeypatch, tmp_path
):
    # M11.3: onceki bir basarisiz calistirmadan kalma bir uyari dosyasi,
    # bir SONRAKI basarili calistirmada temizlenir - boylece dosyanin
    # VARLIGI her zaman "su an cozulmemis" anlamina gelir.
    (tmp_path / "NEEDS_LOGIN.txt").write_text("eski uyari", encoding="utf-8")
    _patch_db(monkeypatch)

    def _fake_build_dependencies(account_id, session, config_dir, reports_dir, secrets_file):
        return "deps"

    monkeypatch.setattr(main, "build_dependencies", _fake_build_dependencies)
    monkeypatch.setattr(main, "run_account", lambda *args, **kwargs: None)

    on_trigger = main._make_on_trigger(Path("config"), tmp_path, Path("secrets.json"))

    on_trigger(uuid4())

    assert not (tmp_path / "NEEDS_LOGIN.txt").exists()


def test_make_on_trigger_session_invalid_error_still_propagates_when_alert_write_fails(
    monkeypatch, tmp_path
):
    # M11.3: `_write_session_alert()`'in kendi "best-effort, orijinal
    # hatayi MASKELEMEZ" garantisini dogrudan dogrular - yazma HATASI
    # (burada: `reports_dir`'in mevcut olmayan bir alt-dizini, `write_text`'in
    # `FileNotFoundError`/`OSError` firlatmasina neden olur) SessionInvalidError'in
    # yukari sizmasini ENGELLEMEMELIDIR.
    engines, sessions = _patch_db(monkeypatch)
    unwritable_reports_dir = tmp_path / "does-not-exist"

    def _fake_build_dependencies(account_id, session, config_dir, reports_dir, secrets_file):
        return "deps"

    def _raise_session_invalid(*args, **kwargs):
        raise SessionInvalidError("oturum gecersiz")

    monkeypatch.setattr(main, "build_dependencies", _fake_build_dependencies)
    monkeypatch.setattr(main, "run_account", _raise_session_invalid)

    on_trigger = main._make_on_trigger(
        Path("config"), unwritable_reports_dir, Path("secrets.json")
    )

    with pytest.raises(SessionInvalidError):
        on_trigger(uuid4())

    assert len(sessions) == 1
    assert sessions[0].rollback_count == 1
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
    monkeypatch.setattr(
        main,
        "run_account",
        lambda account_id, dependencies, now, lock_duration, trigger_type: on_trigger_calls.append(
            (account_id, trigger_type)
        ),
    )

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
