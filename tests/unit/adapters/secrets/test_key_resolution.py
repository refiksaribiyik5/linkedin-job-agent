"""resolve_encryption_key() icin birim testleri (Roadmap M2.3, TDD Section
24: "anahtar OS keychain'den veya kaynak koduna asla girmeyen bir ortam
degiskeninden alinir").

Bu testler GERCEK OS keychain'e dokunmaz - `keyring` modulunun
get_password/set_password fonksiyonlari monkeypatch ile sahtelenir; bu,
CI/otomatik test calistirmalarinin gercek isletim sistemi anahtarligina
(macOS Keychain vb.) hicbir zaman dokunmamasini, dolayisiyla kimlik
dogrulama istemleri veya kalici yan etkiler uretmemesini saglar.
"""

from __future__ import annotations

import keyring.errors
import pytest
from cryptography.fernet import Fernet

from linkedinbot.adapters.secrets import local_keyring_adapter as module_under_test
from linkedinbot.adapters.secrets.local_keyring_adapter import resolve_encryption_key


def test_prefers_env_var_when_set(monkeypatch):
    env_key = Fernet.generate_key().decode()
    monkeypatch.setenv("LINKEDINBOT_SECRETS_ENCRYPTION_KEY", env_key)

    def _keyring_should_not_be_called(*args, **kwargs):
        raise AssertionError("keyring.get_password cagirilmamaliydi - env var oncelikli olmali")

    monkeypatch.setattr(module_under_test.keyring, "get_password", _keyring_should_not_be_called)

    assert resolve_encryption_key() == env_key.encode()


def test_falls_back_to_keyring_when_env_not_set(monkeypatch):
    monkeypatch.delenv("LINKEDINBOT_SECRETS_ENCRYPTION_KEY", raising=False)
    stored_key = Fernet.generate_key().decode()
    monkeypatch.setattr(
        module_under_test.keyring, "get_password", lambda service, username: stored_key
    )

    assert resolve_encryption_key() == stored_key.encode()


def test_generates_and_persists_new_key_when_neither_env_nor_keyring_has_one(monkeypatch):
    monkeypatch.delenv("LINKEDINBOT_SECRETS_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(module_under_test.keyring, "get_password", lambda service, username: None)

    persisted = {}

    def _fake_set_password(service, username, value):
        persisted["service"] = service
        persisted["username"] = username
        persisted["value"] = value

    monkeypatch.setattr(module_under_test.keyring, "set_password", _fake_set_password)

    key = resolve_encryption_key()

    assert persisted["value"] is not None
    assert key == persisted["value"].encode()
    # Uretilen anahtar gecerli bir Fernet anahtari olmalidir (hata firlatmadan kurulabilmeli).
    Fernet(key)


def test_generated_key_is_persisted_so_a_second_call_reuses_it(monkeypatch):
    # Her cagrida yeni bir anahtar uretilirse, ONCEDEN sifrelenmis
    # secret'lar bir daha asla cozulemez hale gelir - bu yuzden uretilen
    # anahtarin GERCEKTEN "saklandigi" (ikinci bir okumanin ayni degeri
    # gormesi gerektigi) davranissal olarak dogrulanir.
    monkeypatch.delenv("LINKEDINBOT_SECRETS_ENCRYPTION_KEY", raising=False)
    fake_keychain: dict[str, str] = {}

    def _fake_get_password(service, username):
        return fake_keychain.get(username)

    def _fake_set_password(service, username, value):
        fake_keychain[username] = value

    monkeypatch.setattr(module_under_test.keyring, "get_password", _fake_get_password)
    monkeypatch.setattr(module_under_test.keyring, "set_password", _fake_set_password)

    first_call = resolve_encryption_key()
    second_call = resolve_encryption_key()

    assert first_call == second_call


def test_get_password_keyring_error_raises_clear_actionable_message(monkeypatch):
    # Ic-denetimde bulunan gercek bulgu: bir keyring backend'i olmayan bir
    # ortamda (orn. bir Docker konteyneri - bu modulun kendi tasarim
    # gerekcesinin ISARET ETTIGI TAM senaryo), keyring.get_password() ham
    # NoKeyringError firlatir - "baska bir backend paketi kurun" diyen,
    # bu depo icin YANLIS yonlendiren, LinkedInBot'a ozgu hicbir baglam
    # tasimayan bir mesaj. Cozum ('LINKEDINBOT_SECRETS_ENCRYPTION_KEY'i
    # ayarlayin) acikca belirtilmelidir.
    monkeypatch.delenv("LINKEDINBOT_SECRETS_ENCRYPTION_KEY", raising=False)

    def _no_backend(service, username):
        raise keyring.errors.NoKeyringError("No recommended backend was available.")

    monkeypatch.setattr(module_under_test.keyring, "get_password", _no_backend)

    with pytest.raises(RuntimeError, match="LINKEDINBOT_SECRETS_ENCRYPTION_KEY"):
        resolve_encryption_key()


def test_set_password_keyring_error_raises_clear_actionable_message(monkeypatch):
    # Ayni bulgu, yeni uretilen anahtarin keychain'e YAZILAMADIGI durum icin.
    monkeypatch.delenv("LINKEDINBOT_SECRETS_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(module_under_test.keyring, "get_password", lambda service, username: None)

    def _cannot_persist(service, username, value):
        raise keyring.errors.PasswordSetError("could not persist")

    monkeypatch.setattr(module_under_test.keyring, "set_password", _cannot_persist)

    with pytest.raises(RuntimeError, match="LINKEDINBOT_SECRETS_ENCRYPTION_KEY"):
        resolve_encryption_key()
