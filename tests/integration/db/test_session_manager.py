"""SessionManager icin entegrasyon testleri (Roadmap M3.1).

Roadmap M3.1 "Beklenen Sonuc": "Bir kez interaktif giris yapildiktan
sonra oturum storage_state olarak Secrets Provider uzerinden saklanir;
surec yeniden baslatildiginda kimlik bilgisi tekrar istenmez." Asagidaki
testler bu davranisi (1) gercek bir DB satiri (`linkedin_sessions`)
uzerinden ve (2) sahte (in-memory) bir SecretsProvider + sahte bir
"interaktif giris" callable'i uzerinden dogrular - gercek Playwright'a
bu dosyada hic dokunulmaz (bkz. test_playwright_client.py, tarayici
tarafi zaten ayri test edildi).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from linkedinbot.adapters.linkedin.session_manager import SessionManager
from linkedinbot.db.models import AccountOrm, LinkedInSessionOrm, SessionStatus
from linkedinbot.ports.linkedin_port import LinkedInPort
from linkedinbot.ports.secrets_provider_port import SecretsProviderPort

FAKE_STORAGE_STATE = {"cookies": [{"name": "li_at", "value": "fake-session-token"}]}


class _FakeSecretsProvider(SecretsProviderPort):
    def __init__(self):
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        self._store[key] = value


@pytest.fixture
def secrets_provider() -> _FakeSecretsProvider:
    return _FakeSecretsProvider()


@pytest.fixture
def playwright_login():
    calls = []

    def _login():
        calls.append(1)
        return FAKE_STORAGE_STATE

    _login.calls = calls
    return _login


@pytest.fixture
def session_manager(
    db_session: Session, secrets_provider: _FakeSecretsProvider, playwright_login
) -> SessionManager:
    return SessionManager(db_session, secrets_provider, playwright_login)


def test_session_manager_implements_linkedin_port(session_manager: SessionManager):
    assert isinstance(session_manager, LinkedInPort)


def test_ensure_session_performs_login_when_no_existing_session(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    playwright_login,
    secrets_provider: _FakeSecretsProvider,
):
    session_manager.ensure_session(account.account_id)

    assert len(playwright_login.calls) == 1

    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row is not None
    assert row.session_status == SessionStatus.VALID
    assert row.last_validated_at is not None
    assert row.encrypted_storage_state_ref is not None

    persisted = secrets_provider.get(row.encrypted_storage_state_ref)
    assert json.loads(persisted) == FAKE_STORAGE_STATE


def test_ensure_session_skips_login_when_session_already_persisted(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    playwright_login,
):
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref="linkedin_storage_state:already-there",
            session_status=SessionStatus.VALID,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    session_manager.ensure_session(account.account_id)

    # Roadmap M3.1'in tam olarak istedigi sey: kimlik bilgisi TEKRAR
    # istenmez - interaktif giris callable'i hic cagirilmamali.
    assert playwright_login.calls == []


def test_ensure_session_updates_placeholder_row_missing_a_session_ref(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    playwright_login,
    secrets_provider: _FakeSecretsProvider,
):
    # `encrypted_storage_state_ref` nullable'dir (bkz. db/models.py) - bir
    # hesap olusturulup ilk giris yapilmasi arasinda boyle bir "yer
    # tutucu" satir teorik olarak var olabilir. Bu durumda M3.1 hala
    # giris yapip AYNI satiri guncellemelidir (yeni bir satir eklemeye
    # calisip PK ihlali uretmemelidir).
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref=None,
            session_status=SessionStatus.UNKNOWN,
            last_validated_at=None,
        )
    )
    db_session.flush()

    session_manager.ensure_session(account.account_id)

    assert len(playwright_login.calls) == 1
    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row.session_status == SessionStatus.VALID
    assert row.encrypted_storage_state_ref is not None
    assert json.loads(secrets_provider.get(row.encrypted_storage_state_ref)) == FAKE_STORAGE_STATE


def test_ensure_session_leaves_no_partial_state_when_login_fails(
    db_session: Session,
    account: AccountOrm,
    secrets_provider: _FakeSecretsProvider,
):
    # Ic-denetimde dogrulanmasi gereken bir davranis (kodun kendisi zaten
    # dogru sirayla yaziliyor, ama bu oncesinde otomatik bir test yoktu):
    # giris basarisiz olursa (orn. LoginTimeoutError - kullanici 2FA'yi
    # tamamlamadan vazgecti), NE bir DB satiri NE de bir secret
    # yazilmamalidir - basarisiz bir girisin yarim/tutarsiz bir "oturum
    # var" izlenimi birakmasi, sonraki bir calistirmanin gecersiz/eksik
    # bir referansla calismaya calismasina yol acardi.
    def _failing_login():
        raise RuntimeError("kullanici 2FA'yi tamamlamadan vazgecti")

    manager = SessionManager(db_session, secrets_provider, _failing_login)

    with pytest.raises(RuntimeError, match="2FA"):
        manager.ensure_session(account.account_id)

    assert db_session.get(LinkedInSessionOrm, account.account_id) is None
    assert secrets_provider._store == {}
