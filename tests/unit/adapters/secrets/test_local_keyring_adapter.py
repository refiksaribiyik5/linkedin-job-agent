"""LocalKeyringSecretsProvider icin birim testleri (Roadmap M2.3).

Roadmap M2.3 "Tamamlanma Dogrulamasi": "Birim testi round-trip yapar; disk
dosyasi dogrudan acilarak (hex/binary dump) duz metin secret'in gorunmedigi
manuel olarak teyit edilir." Asagidaki testler round-trip'i VE disk
dosyasinin duz metin icermedigini (manuel degil, otomatik bir regresyon
testi olarak - tek seferlik manuel teyitten daha guclu ve kalici) dogrular.

Bu testler GERCEK OS keychain'e DOKUNMAZ - `encryption_key` dogrudan
constructor'a enjekte edilir (bkz. adapter'in kendi tasarim gerekcesi);
keychain/env degiskeni cozumleme mantigi (`resolve_encryption_key`) ayri,
kendi test dosyasinda (test_key_resolution.py) mock'lanarak test edilir.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet, InvalidToken

from linkedinbot.adapters.secrets.local_keyring_adapter import LocalKeyringSecretsProvider
from linkedinbot.ports.secrets_provider_port import SecretsProviderPort


@pytest.fixture
def encryption_key() -> bytes:
    return Fernet.generate_key()


@pytest.fixture
def secrets_file(tmp_path: Path) -> Path:
    return tmp_path / "secrets.enc"


@pytest.fixture
def provider(secrets_file: Path, encryption_key: bytes) -> LocalKeyringSecretsProvider:
    return LocalKeyringSecretsProvider(secrets_file, encryption_key)


def test_provider_implements_port(provider: LocalKeyringSecretsProvider):
    assert isinstance(provider, SecretsProviderPort)


def test_get_returns_none_for_unknown_key(provider: LocalKeyringSecretsProvider):
    assert provider.get("anthropic_api_key") is None


def test_set_then_get_round_trips(provider: LocalKeyringSecretsProvider):
    provider.set("anthropic_api_key", "sk-ant-super-secret-value")
    assert provider.get("anthropic_api_key") == "sk-ant-super-secret-value"


def test_set_overwrites_existing_value(provider: LocalKeyringSecretsProvider):
    provider.set("anthropic_api_key", "old-value")
    provider.set("anthropic_api_key", "new-value")
    assert provider.get("anthropic_api_key") == "new-value"


def test_multiple_keys_stored_independently(provider: LocalKeyringSecretsProvider):
    provider.set("anthropic_api_key", "value-a")
    provider.set("linkedin_storage_state", "value-b")
    assert provider.get("anthropic_api_key") == "value-a"
    assert provider.get("linkedin_storage_state") == "value-b"


def test_disk_file_does_not_contain_plaintext_secret(
    provider: LocalKeyringSecretsProvider, secrets_file: Path
):
    # Roadmap M2.3 "Tamamlanma Dogrulamasi"nin otomatiklestirilmis hali:
    # dosyanin HAM BYTE'LARI dogrudan okunur, plaintext'in hicbir yerde
    # gorunmedigi dogrulanir (hex/binary dump'in programatik esdegeri).
    distinctive_secret = "sk-ant-VERY-DISTINCTIVE-PLAINTEXT-MARKER-123456"
    provider.set("anthropic_api_key", distinctive_secret)

    raw_bytes = secrets_file.read_bytes()

    assert distinctive_secret.encode() not in raw_bytes
    assert b"VERY-DISTINCTIVE-PLAINTEXT-MARKER" not in raw_bytes


def test_persists_across_separate_provider_instances(secrets_file: Path, encryption_key: bytes):
    # Kalicilik gercekten diske mi yaziliyor, yoksa yalnizca bellek-ici bir
    # onbellek mi? Ayri bir provider ORNEGI ayni dosya+anahtarla kurulup
    # onceki yazilani okuyabilmelidir.
    writer = LocalKeyringSecretsProvider(secrets_file, encryption_key)
    writer.set("anthropic_api_key", "persisted-value")

    reader = LocalKeyringSecretsProvider(secrets_file, encryption_key)
    assert reader.get("anthropic_api_key") == "persisted-value"


def test_wrong_encryption_key_cannot_decrypt(secrets_file: Path, encryption_key: bytes):
    # Sifrelemenin GERCEKTEN kriptografik oldugunu (salt gizleme/obfuscation
    # degil) kanitlar - yanlis anahtarla okuma girisimi acikca basarisiz
    # olmalidir, sessizce bozuk/yanlis bir deger DONDURMEMELIDIR.
    writer = LocalKeyringSecretsProvider(secrets_file, encryption_key)
    writer.set("anthropic_api_key", "top-secret-value")

    wrong_key = Fernet.generate_key()
    reader = LocalKeyringSecretsProvider(secrets_file, wrong_key)

    with pytest.raises(InvalidToken):
        reader.get("anthropic_api_key")


def test_wrong_key_error_message_names_the_key_and_file(secrets_file: Path, encryption_key: bytes):
    # Ic-denetimde bulunan bulgu: ham InvalidToken hicbir baglam tasimaz
    # (hangi secret, hangi dosya) - "yanlis anahtar" ile "bozuk dosya"
    # ayirt edilemez oluyordu. Hata mesaji artik anahtar adini ve dosya
    # yolunu acikca icermelidir.
    writer = LocalKeyringSecretsProvider(secrets_file, encryption_key)
    writer.set("anthropic_api_key", "top-secret-value")

    reader = LocalKeyringSecretsProvider(secrets_file, Fernet.generate_key())

    with pytest.raises(InvalidToken, match="anthropic_api_key") as exc_info:
        reader.get("anthropic_api_key")
    assert str(secrets_file) in str(exc_info.value)


def test_corrupted_secrets_file_raises_clear_error_naming_the_file(
    provider: LocalKeyringSecretsProvider, secrets_file: Path
):
    # Ic-denetimde bulunan bulgu: json.loads() ham JSONDecodeError
    # firlatiyordu - hangi dosyanin bozuk oldugu belirtilmeden.
    secrets_file.parent.mkdir(parents=True, exist_ok=True)
    secrets_file.write_text("this is not valid json{{{")

    with pytest.raises(ValueError, match=str(secrets_file)):
        provider.get("anthropic_api_key")


def test_secrets_directory_is_not_readable_by_group_or_others(
    tmp_path: Path, encryption_key: bytes
):
    # Ic-denetimde bulunan bulgu: dosya 0o600 ile korunurken, onu iceren
    # dizin varsayilan (genellikle grup/digerleri tarafindan listelenebilir)
    # izinlerle olusturuluyordu - dosyanin ADI (icerigi degil) baska yerel
    # kullanicilar tarafindan kesfedilebilir kaliyordu. pytest'in kendi
    # `tmp_path`'i zaten kisitli izinlerle geldigi icin (fixture'in
    # KENDISI dogru sonucu maskeleyebilir), burada BILEREK YENI, ic-ice
    # bir alt dizin kullanilir - boylece izin, pytest'ten degil, adaptorun
    # KENDI `mkdir()` cagrisindan geldigi kanitlanir.
    nested_path = tmp_path / "brand-new-nested-dir" / "secrets.enc"
    provider = LocalKeyringSecretsProvider(nested_path, encryption_key)

    provider.set("anthropic_api_key", "value")

    mode = nested_path.parent.stat().st_mode
    assert not (mode & 0o077), f"secrets dizini grup/digerleri tarafindan erisilebilir: {oct(mode)}"


def test_secrets_file_is_not_readable_by_group_or_others(
    provider: LocalKeyringSecretsProvider, secrets_file: Path
):
    provider.set("anthropic_api_key", "value")
    mode = secrets_file.stat().st_mode
    assert not (mode & 0o077), f"secrets dosyasi grup/digerleri tarafindan okunabilir: {oct(mode)}"


def test_creates_parent_directory_if_missing(tmp_path: Path, encryption_key: bytes):
    nested_path = tmp_path / "nested" / "dir" / "secrets.enc"
    provider = LocalKeyringSecretsProvider(nested_path, encryption_key)

    provider.set("anthropic_api_key", "value")

    assert nested_path.exists()


def test_no_leftover_temp_file_after_successful_write(
    provider: LocalKeyringSecretsProvider, secrets_file: Path
):
    # Ic-denetimde bulunan atomik-yazma duzeltmesinin bir yan etkisi:
    # gecici dosya basariyla os.replace() ile hedefe tasindiktan sonra
    # ayni dizinde ARTIK var olmamalidir.
    provider.set("anthropic_api_key", "value")

    leftover_temp_files = list(secrets_file.parent.glob(".secrets-*.tmp"))
    assert leftover_temp_files == []


def test_original_file_is_untouched_if_write_fails_partway(
    provider: LocalKeyringSecretsProvider, secrets_file: Path, monkeypatch
):
    # Ic-denetimde bulunan gercek bulgu: duz write_text() atomik degildi -
    # yazma sirasindaki bir kesinti TUM onceki secret'lari (yalnizca o an
    # yazilani degil) bozuk/okunamaz hale getirebilirdi. Bu test, kismi
    # bir yazma HATASININ orijinal dosyayi DEGISTIRMEDEN birakildigini
    # kanitlar (atomik temp-dosya + os.replace deseni sayesinde).
    provider.set("anthropic_api_key", "original-value")
    original_bytes = secrets_file.read_bytes()

    def _boom(*args, **kwargs):
        raise OSError("simulated disk failure mid-write")

    monkeypatch.setattr("os.replace", _boom)

    with pytest.raises(OSError, match="simulated disk failure"):
        provider.set("anthropic_api_key", "new-value-that-should-never-land")

    assert secrets_file.read_bytes() == original_bytes
    assert provider.get("anthropic_api_key") == "original-value"
    # Basarisiz denemenin gecici dosyasi da ardinda birakilmamis olmali.
    assert list(secrets_file.parent.glob(".secrets-*.tmp")) == []
