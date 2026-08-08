"""LocalKeyringSecretsProvider - SecretsProviderPort'un V1 uygulamasi
(Roadmap M2.3, TDD Section 24).

TDD Section 24 "Saklama mekanizmasi": "`SecretsProvider` Port; V1 uygulamasi
(`LocalKeyringSecretsProvider`) verileri simetrik sifreleme (anahtar OS
keychain'den veya kaynak koduna asla girmeyen bir ortam degiskeninden
alinir) ile diskte sifreli tutar."

Bu tek cumle iki AYRI sorumlulugu tanimlar, bu modulde bilincli olarak
IKI AYRI parcaya bolunmustur:

1. **Secret'larin kendisi diskte sifreli saklanir** (`LocalKeyringSecretsProvider`
   sinifi) - Fernet (AES128-CBC + HMAC, dogrulanmis simetrik sifreleme,
   `cryptography` kutuphanesi) ile. Bu sinif, sifreleme ANAHTARINI
   constructor'dan (`encryption_key: bytes`) doğrudan alir - KENDİSİ
   anahtari nereden bulacagina KARAR VERMEZ. Bu, testedilebilirlik icin
   bilincli bir tasarim kararidir: gercek OS keychain'e dokunmadan, bilinen
   bir test anahtariyla tam round-trip/yanlis-anahtar/kalicilik testleri
   yapilabilir (bkz. test_local_keyring_adapter.py).

2. **Anahtarin KENDISI OS keychain'den veya bir ortam degiskeninden
   gelir** (`resolve_encryption_key()` fonksiyonu) - `keyring` kutuphanesi
   araciligiyla. Bu, AYRI bir fonksiyondur ki (a) `LocalKeyringSecretsProvider`
   saf bir sifreleme/dosya-IO bileseni olarak kalsin, (b) bu cozumleme
   mantigi kendi basina, gercek keychain'e dokunmadan mock'lanarak test
   edilebilsin (bkz. test_key_resolution.py). Oncelik: ortam degiskeni
   (varsa) > keychain'deki mevcut anahtar > (hicbiri yoksa) yeni uretilip
   keychain'e kalici olarak yazilan bir anahtar. Ortam degiskeninin
   keychain'den ONCE kontrol edilmesi, TDD Section 27'nin hedeflediği
   Docker dagitimi icin onemlidir - bir Linux konteynerinde genellikle
   calisan bir OS keychain servisi (macOS Keychain, GNOME Keyring vb.)
   YOKTUR; ortam degiskeni bu ortamlarin GERCEKTEN calisabilecegi tek
   yoldur (bkz. TDD Section 27 "Konfigurasyon/secrets .env... uzerinden
   enjekte edilir").

Dosya formati: JSON ile encode edilmis bir `{anahtar: fernet-token}` sozlugu.
Anahtar ADLARI (orn. "anthropic_api_key") plaintext olarak JSON'da durur -
bunlar zaten secret DEGILDIR, yalnizca hangi secret'in hangi oldugunu
ayirt eden etiketlerdir. Her DEGER ayri ayri sifrelenir (tek bir secret'i
guncellemek digerlerini yeniden sifrelemeyi gerektirmez).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import keyring
import keyring.errors
from cryptography.fernet import Fernet, InvalidToken

from linkedinbot.ports.secrets_provider_port import SecretsProviderPort

_ENV_VAR_NAME = "LINKEDINBOT_SECRETS_ENCRYPTION_KEY"
_KEYRING_SERVICE_NAME = "linkedinbot"
_KEYRING_USERNAME = "secrets-encryption-key"

def _keyring_unavailable_message(cause: BaseException) -> str:
    return (
        f"OS keychain'e erisilemedi ({cause}). Bu genellikle bir OS keychain "
        f"servisinin calismadigi bir ortamda (orn. bir Docker konteyneri, bkz. "
        f"TDD Section 27) olusur - byle bir ortamda '{_ENV_VAR_NAME}' ortam "
        f"degiskenini gecerli bir Fernet anahtariyla acikca ayarlayin "
        f"(bkz. .env.example)."
    )


def resolve_encryption_key() -> bytes:
    """Sifreleme anahtarini TDD Section 24'un belirttigi sekilde cozer:
    once ortam degiskeni, sonra OS keychain, hicbiri yoksa yeni uretilip
    keychain'e kalici olarak yazilan bir anahtar (bkz. modul dokumani).

    `keyring.errors.KeyringError` (orn. hicbir backend bulunamadigi
    `NoKeyringError` - ic-denetimde ampirik olarak dogrulanmis, TAM OLARAK
    TDD Section 27'nin hedefledigi Docker senaryosunda olusan bir hata)
    acikca yakalanip, bu depoya ozel, dogru duzeltmeyi (env degiskenini
    ayarlamak) gosteren bir `RuntimeError`'a donusturulur - ham keyring
    hatasi, kullaniciyi YANLIS bir duzeltmeye (baska bir keyring backend'i
    kurmaya) yonlendirebilecek genel bir mesaj tasir.
    """
    env_value = os.environ.get(_ENV_VAR_NAME)
    if env_value:
        return env_value.encode()

    try:
        existing = keyring.get_password(_KEYRING_SERVICE_NAME, _KEYRING_USERNAME)
    except keyring.errors.KeyringError as exc:
        raise RuntimeError(_keyring_unavailable_message(exc)) from exc

    if existing:
        return existing.encode()

    new_key = Fernet.generate_key()
    try:
        keyring.set_password(_KEYRING_SERVICE_NAME, _KEYRING_USERNAME, new_key.decode())
    except keyring.errors.KeyringError as exc:
        raise RuntimeError(_keyring_unavailable_message(exc)) from exc
    return new_key


class LocalKeyringSecretsProvider(SecretsProviderPort):
    def __init__(self, secrets_file_path: Path, encryption_key: bytes) -> None:
        self._secrets_file_path = secrets_file_path
        self._fernet = Fernet(encryption_key)

    def get(self, key: str) -> str | None:
        encrypted_values = self._read_all()
        token = encrypted_values.get(key)
        if token is None:
            return None
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            # Ic-denetimde bulunan bulgu: ham InvalidToken hicbir baglam
            # tasimaz (Fernet, guvenlik geregi bos birakir) - "yanlis
            # anahtar" ile "bozuk dosya" ayirt edilemez oluyordu.
            raise InvalidToken(
                f"'{key}' secret'i cozulemedi ({self._secrets_file_path}) - "
                "yanlis sifreleme anahtari veya bozuk secrets dosyasi."
            ) from exc

    def set(self, key: str, value: str) -> None:
        encrypted_values = self._read_all()
        encrypted_values[key] = self._fernet.encrypt(value.encode()).decode()
        self._write_all(encrypted_values)

    def _read_all(self) -> dict[str, str]:
        # `.exists()` sonra `.read_text()` (check-then-act) bir TOCTOU
        # penceresi acardi (ic-denetimde bulunan bulgu): dosya iki cagri
        # arasinda silinirse `FileNotFoundError` sizardi. Bunun yerine
        # dogrudan okumayi dene, eksikligi (EAFP) yakala - hem daha kisa
        # hem yarissiz.
        try:
            raw_text = self._secrets_file_path.read_text()
        except FileNotFoundError:
            return {}
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Secrets dosyasi okunamadi/bozuk: {self._secrets_file_path}"
            ) from exc

    def _write_all(self, encrypted_values: dict[str, str]) -> None:
        """Atomik yazma: gecici bir dosyaya yazip `os.replace()` ile hedefin
        yerine ATOMIK olarak koyar - duz `write_text()` DEGIL.

        Iki ayri sorunu birden cozer: (1) `write_text()` atomik degildir;
        yazma sirasinda surec kesintiye ugrarsa (crash, guc kesintisi)
        dosya YARIM/BOZUK JSON olarak kalir ve bir sonraki okuma TUM
        secret'lari (yalnizca o an yazilani degil) kaybettirir - NFR-13'un
        "ya butunuyle uygulanir ya da hic uygulanmaz" ilkesinin bu kucuk
        dosyaya da uygulanmasi gerekir. (2) `write_text()` sonra `chmod()`
        cagirmak, dosyanin varsayilan (potansiyel olarak grup/digerleri
        tarafindan okunabilir) izinlerle KISA bir sure var oldugu bir
        yaris durumu (TOCTOU) yaratirdi; `tempfile.mkstemp()` dosyayi
        BASTAN itibaren yalnizca sahibi tarafindan okunabilir/yazilabilir
        (0o600) olarak olusturur (Python'in belgelenmis garantisi) ve
        `os.replace()` bu izinleri hedefe tasirken korur - hicbir izin
        penceresi acilmaz.

        NOT (ic-denetimde bulunup KASITLI OLARAK COZULMEMIS bir sinirlama):
        bu metod, `_read_all()` + `_write_all()` cifti arasinda hicbir
        kilitleme yapmaz - iki YAZMA cagrisi (`set()`) TAM OLARAK ayni anda
        calisirsa "kaybolan guncelleme" riski teorik olarak vardir. Bu
        bilerek eklenmedi: V1'de RunLock (M9.1, henuz yok) zaten es zamanli
        pipeline calistirmalarini engeller ve TDD Section 24'un tanimladigi
        iki secret sinifi da (LLM API anahtari, LinkedIn oturumu) dogasi
        geregi nadir/tek-seferlik/elle yazilir - bugun hicbir gercek
        cagiran (M3.1/M5.1 henuz yok) yok. Bir kilitleme mekanizmasi simdi
        eklemek, henuz var olmayan tuketicilerin nasil davranacagini tahmin
        ederek erken optimizasyon olurdu; ikinci gercek cagiran eklendiginde
        yeniden degerlendirilmelidir.

        Dizin izinleri de dosyayla AYNI mantikla sikilastirilir - dosya
        0o600 olsa bile, onu iceren dizin varsayilan izinlerle (genellikle
        grup/digerleri tarafindan LISTELENEBILIR) olusturuluyordu; bu,
        icerigi degil ama secrets dosyasinin ADININ var oldugunu baska
        yerel kullanicilara ifsa ederdi.
        """
        self._secrets_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._secrets_file_path.parent.chmod(0o700)
        payload = json.dumps(encrypted_values)

        fd, tmp_path_str = tempfile.mkstemp(
            dir=self._secrets_file_path.parent, prefix=".secrets-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as tmp_file:
                tmp_file.write(payload)
            os.replace(tmp_path_str, self._secrets_file_path)
        except BaseException:
            Path(tmp_path_str).unlink(missing_ok=True)
            raise
