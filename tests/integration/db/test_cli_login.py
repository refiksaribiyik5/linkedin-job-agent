"""`cli.py::_run_login_command()` icin GERCEK DB entegrasyon testleri (Faz
13, adversarial review'da bulunan blocker'in regresyon koruyucusu).

Blocker: `_run_login_command()`, basarili bir interaktif giris SONRASI
`linkedin_sessions` tablosuna HICBIR sey yazmiyordu - bu, hic
`LinkedInSessionOrm` satiri olmayan bir hesap icin (orn. ilk giris),
`SessionManager.validate()`'in "existing is None -> SessionInvalidError"
guvenlik aginin, GERCEKTEN gecerli olan profili canli kontrol ETMEDEN
reddetmesine yol aciyordu - M10.2'nin duzelttigi "kendi kendine asla
iyilesemeyen kalici kilitlenme" hata sinifinin farkli bir kod yolundan
geri gelmesi.

`tests/unit/test_cli.py`, `RunLock`/`SqlAlchemyAccountRepository`/
`perform_interactive_login`'i TAMAMEN sahteler (birim test, DB'ye hic
dokunmaz) - ama tam da bu sahtelerin GIZLEYEBILECEGI turden bir kusurdu
bu (bkz. `tests/integration/db/test_main_session_alert.py`'nin AYNI
gerekcesi). Bu dosya GERCEK bir DB + GERCEK `RunLock` + GERCEK
`SessionManager.validate()` kullanir - yalnizca `perform_interactive_login`
(gercek Playwright/Chromium/LinkedIn'e HICBIR ZAMAN dokunulmaz) sahtelenir.

`_run_login_command()` KENDI AYRI engine/session'ini acar (cli.py'nin
`_run_run_command`/main.py'nin `_on_trigger`'iyla AYNI desen) - bu yuzden
`db_session` fixture'inda yapilan onceki yazilarin GORULEBILMESI icin
`db_session.commit()` SARTTIR (aksi halde farkli bir DB baglantisi
henuz-commit-edilmemis satirlari GOREMEZ) - bkz.
test_main_session_alert.py'nin AYNI notu.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from linkedinbot import cli
from linkedinbot.adapters.linkedin.playwright_client import LoginTimeoutError
from linkedinbot.adapters.linkedin.session_manager import SessionManager
from linkedinbot.db.models import AccountOrm, LinkedInSessionOrm, RunLockOrm, SessionStatus
from linkedinbot.ports.linkedin_port import SessionInvalidError
from linkedinbot.run.run_lock import RunLock


def _install_runlock_spy(monkeypatch):
    """Gercek `RunLock` davranisini KORUYARAK (delegasyonla) `acquire()`/
    `release()` cagrilarini sayar - madde D'nin "nested RunLock alinmiyor"
    iddiasini, gercek DB uzerinde calisan GERCEK bir RunLock ile dogrudan
    kanitlamak icin."""
    acquire_calls: list[tuple] = []
    release_calls: list[tuple] = []

    class _SpyRunLock(RunLock):
        def acquire(self, account_id, lock_owner, now, lock_duration):
            acquire_calls.append((account_id, lock_owner))
            return super().acquire(account_id, lock_owner, now, lock_duration)

        def release(self, account_id, lock_owner):
            release_calls.append((account_id, lock_owner))
            return super().release(account_id, lock_owner)

    monkeypatch.setattr(cli, "RunLock", _SpyRunLock)
    return acquire_calls, release_calls


def _install_fake_login(monkeypatch, *, raise_timeout: bool = False):
    """`perform_interactive_login()`'i sahteler - gercek Playwright/Chromium/
    LinkedIn'e HICBIR ZAMAN dokunulmaz. Basarili durumda, GERCEK
    `perform_interactive_login()`'in yaptigi gibi profil dizinini olusturur
    (madde 5: "persistent profile gercekten olusmus olmali")."""
    login_calls: list[Path] = []

    def _fake(profile_dir: Path) -> None:
        login_calls.append(profile_dir)
        if raise_timeout:
            raise LoginTimeoutError("Interaktif LinkedIn girisi zaman asimina ugradi")
        profile_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(cli, "perform_interactive_login", _fake)
    return login_calls


# ---------------------------------------------------------------------------
# A) Hic linkedin_sessions satiri olmayan bir hesap icin basarili giris.
# ---------------------------------------------------------------------------


def test_login_creates_session_row_for_account_with_no_prior_session(
    db_session: Session, account: AccountOrm, tmp_path, monkeypatch
):
    assert db_session.get(LinkedInSessionOrm, account.account_id) is None
    db_session.commit()

    login_calls = _install_fake_login(monkeypatch)
    profile_root = tmp_path / "browser-profile"

    exit_code = cli._run_login_command(account.account_id, profile_root)

    assert exit_code == 0
    assert login_calls == [profile_root / str(account.account_id)]

    db_session.expire_all()
    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row is not None
    assert row.session_status == SessionStatus.VALID
    assert row.last_validated_at is not None
    # (madde G) encrypted_storage_state_ref'e HICBIR ZAMAN deger yazilmaz.
    assert row.encrypted_storage_state_ref is None


# ---------------------------------------------------------------------------
# B) Mevcut (orn. EXPIRED) bir satiri olan hesap icin basarili giris -
# satir GUNCELLENIR, ikinci bir satir OLUSTURULMAZ.
# ---------------------------------------------------------------------------


def test_login_updates_existing_session_row_without_creating_duplicate(
    db_session: Session, account: AccountOrm, tmp_path, monkeypatch
):
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref=None,
            session_status=SessionStatus.EXPIRED,
            last_validated_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    db_session.commit()

    _install_fake_login(monkeypatch)
    profile_root = tmp_path / "browser-profile"

    exit_code = cli._run_login_command(account.account_id, profile_root)

    assert exit_code == 0
    db_session.expire_all()
    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row.session_status == SessionStatus.VALID
    assert row.last_validated_at > datetime(2020, 1, 1, tzinfo=UTC)
    assert row.encrypted_storage_state_ref is None

    # Duplicate satir OLUSMADI - `linkedin_sessions.account_id` PRIMARY KEY
    # oldugu icin bu zaten DB seviyesinde imkansiz olurdu (IntegrityError),
    # ama acikca sayarak da dogrulanir.
    count = (
        db_session.query(LinkedInSessionOrm)
        .filter(LinkedInSessionOrm.account_id == account.account_id)
        .count()
    )
    assert count == 1


# ---------------------------------------------------------------------------
# C) Interaktif giris BASARISIZ olursa VALID yazilmaz.
# ---------------------------------------------------------------------------


def test_login_does_not_write_valid_session_when_login_times_out(
    db_session: Session, account: AccountOrm, tmp_path, monkeypatch
):
    _install_fake_login(monkeypatch, raise_timeout=True)
    profile_root = tmp_path / "browser-profile"
    db_session.commit()

    exit_code = cli._run_login_command(account.account_id, profile_root)

    assert exit_code == 1
    db_session.expire_all()
    assert db_session.get(LinkedInSessionOrm, account.account_id) is None


def test_login_does_not_downgrade_existing_expired_row_on_failure(
    db_session: Session, account: AccountOrm, tmp_path, monkeypatch
):
    # Mevcut EXPIRED bir satir varken giris BASARISIZ olursa, satir EXPIRED
    # olarak KALMALIDIR - yanlislikla VALID'e cekilmemelidir.
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref=None,
            session_status=SessionStatus.EXPIRED,
            last_validated_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    )
    db_session.commit()

    _install_fake_login(monkeypatch, raise_timeout=True)
    profile_root = tmp_path / "browser-profile"

    exit_code = cli._run_login_command(account.account_id, profile_root)

    assert exit_code == 1
    db_session.expire_all()
    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row.session_status == SessionStatus.EXPIRED


# ---------------------------------------------------------------------------
# D) Login zaten RunLock tuttugu icin, DB-yazma cagrisi (mark_session_valid)
# IKINCI bir RunLock.acquire() denemesi YAPMAZ - tek acquire/release cifti.
# ---------------------------------------------------------------------------


def test_login_acquires_and_releases_runlock_exactly_once(
    db_session: Session, account: AccountOrm, tmp_path, monkeypatch
):
    acquire_calls, release_calls = _install_runlock_spy(monkeypatch)
    _install_fake_login(monkeypatch)
    profile_root = tmp_path / "browser-profile"
    db_session.commit()

    exit_code = cli._run_login_command(account.account_id, profile_root)

    assert exit_code == 0
    assert len(acquire_calls) == 1
    assert len(release_calls) == 1
    assert acquire_calls[0][0] == account.account_id
    assert release_calls[0] == acquire_calls[0]

    # Kilit gercekten serbest birakildi (bir sonraki calistirma icin engel
    # kalmadi).
    db_session.expire_all()
    lock_row = db_session.get(RunLockOrm, account.account_id)
    assert lock_row is not None
    assert lock_row.lock_owner is None
    assert lock_row.locked_at is None


# ---------------------------------------------------------------------------
# E) Basarili giris SONRASI olusan DB state, GERCEK SessionManager.validate()
# tarafindan kabul edilebilir (SessionInvalidError FIRLATMAZ) - blocker'in
# DOGRUDAN regresyon testi.
# ---------------------------------------------------------------------------


def test_after_successful_login_validate_does_not_raise_session_invalid_error(
    db_session: Session, account: AccountOrm, tmp_path, monkeypatch
):
    assert db_session.get(LinkedInSessionOrm, account.account_id) is None
    db_session.commit()

    _install_fake_login(monkeypatch)
    profile_root = tmp_path / "browser-profile"

    exit_code = cli._run_login_command(account.account_id, profile_root)
    assert exit_code == 0
    db_session.expire_all()

    # `validate()` icin AYRI bir SessionManager - `check_session_is_valid`
    # sahtelenir (gercek LinkedIn'e HICBIR ZAMAN dokunulmaz), YALNIZCA
    # "existing is None -> erken red" guvenlik agi tetiklenmiyor mu diye
    # sinanir.
    session_manager = SessionManager(
        db_session,
        profile_root,
        lambda _p: None,
        lambda _p: True,  # canli kontrol BASARILI simule edilir
        lambda *_a: [],
    )

    session_manager.validate(account.account_id)  # SessionInvalidError FIRLATMAMALI

    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row.session_status == SessionStatus.VALID


def test_before_fix_scenario_would_have_raised_without_db_row(
    db_session: Session, account: AccountOrm, tmp_path
):
    # Kontrast testi (regresyonu somutlastirir): eger DB satiri HICBIR ZAMAN
    # olusturulmasaydi (duzeltme ONCESI davranis), profil diskte GERCEKTEN
    # var olsa BILE `validate()` canli kontrolu hic DENEMEDEN
    # SessionInvalidError firlatirdi.
    profile_root = tmp_path / "browser-profile"
    profile_dir = profile_root / str(account.account_id)
    profile_dir.mkdir(parents=True)  # profil GERCEKTEN var - ama DB satiri YOK

    session_manager = SessionManager(
        db_session, profile_root, lambda _p: None, lambda _p: True, lambda *_a: []
    )

    with pytest.raises(SessionInvalidError):
        session_manager.validate(account.account_id)


# ---------------------------------------------------------------------------
# F) Profil yolu hesap-bazli kalir (madde F).
# ---------------------------------------------------------------------------


def test_login_uses_account_scoped_profile_path(
    db_session: Session, account: AccountOrm, tmp_path, monkeypatch
):
    login_calls = _install_fake_login(monkeypatch)
    profile_root = tmp_path / "browser-profile"
    db_session.commit()

    cli._run_login_command(account.account_id, profile_root)

    assert login_calls == [profile_root / str(account.account_id)]
    assert login_calls[0].name == str(account.account_id)
    assert login_calls[0].parent == profile_root
