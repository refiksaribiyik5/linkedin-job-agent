"""SessionManager - `linkedin_port`'un implementasyonu (Roadmap M3.1: login
+ kaydetme; Roadmap M3.2: oturum dogrulama; Roadmap M3.3: arama sayfasi
getirme).

TDD Section 9: "SessionManager - `linkedin_port`'un bir parcasi; Playwright'in
`storage_state` (cerezler + local storage) mekanizmasiyla kalici oturumu
yukler/dogrular." Bu sinif o tanimin ucu asamada teslim edilen kismini
karsilar:

- `ensure_session()` (M3.1; M10.2 duzeltmesi: referans VARLIGI degil,
  GECERLILIGI kontrol edilir - bkz. metodun kendi dokumani): verilen hesap
  icin DB'de (`linkedin_sessions`) GECERLI kalici bir oturum yoksa (hic
  referans yok, `session_status=EXPIRED` olarak bilinen, veya `validate()`
  canli kontrolunde basarisiz olan) `playwright_client.perform_interactive_login`'i
  (constructor'dan enjekte edilen bir callable olarak) tetikler, sonucu
  Secrets Provider'a yazar ve DB satirini gunceller/olusturur.
- `validate()` (M3.2, FR-1): kalici bir oturumun HALA gecerli olup
  olmadigini, kayitli `storage_state`'i `playwright_client.check_session_is_valid`'e
  (yine enjekte edilen bir callable olarak) vererek canli kontrol eder.
  Gecersiz/eksik bir oturum sessizce yutulmaz - `SessionInvalidError`
  firlatilir; `session_status`/`last_validated_at` DB alanlari (TDD
  Section 15'in tam da bu amacla tanimladigi kolonlar) sonuca gore
  guncellenir.
- `search_jobs_page()` (M3.3, FR-21): kayitli `storage_state`'i
  `playwright_client.fetch_search_results_page`'e (yine enjekte edilen
  bir callable olarak) vererek TEK bir sayfalik ham ilan karti HTML'sini
  getirir. Sayfalama/limit MANTIGI burada YOKTUR - bu, `collection/collector.py`'nin
  (PaginationController) sorumlulugudur; bu metod yalnizca "kalici oturumu
  bul, secret'i coz, tek sayfa getir" orkestrasyonunu yapar - `ensure_session()`/
  `validate()` ile AYNI "oturum yoksa/referans kirikca SessionInvalidError"
  guvenlik agini paylasir.

DB semasinin kendi belgeledigi gibi (bkz. db/models.py
`LinkedInSessionOrm.encrypted_storage_state_ref`), bu tabloya yazilan
deger ham storage_state DEGIL, Secrets Provider'daki gercek degere
giden bir REFERANS (anahtar adi)dir - ham veri hicbir zaman DB'ye
yazilmaz, yalnizca sifreli secrets deposuna (bkz. adapters.secrets).

DI deseni, kod tabaninin geri kalaniyla tutarlidir (bkz. cli.seed(),
LocalKeyringSecretsProvider): `Session` ve `SecretsProviderPort`
constructor'dan enjekte edilir (kendi kendine olusturulmaz); `account_id`
ise (repository'lerin `create()` metodlariyla ayni desende) HER cagriya
parametre olarak verilir, constructor'a gomulmez - TDD Section 14'un
"account_id parametresi olmadan hicbir Account-Scoped sorgu calismaz"
ilkesiyle tutarli. Bu sinif kendi basina COMMIT ETMEZ - transaction
sinirini cagiran yonetir (ayni `seed()` konvansiyonu).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from linkedinbot.db.models import LinkedInSessionOrm, SessionStatus
from linkedinbot.ports.linkedin_port import LinkedInPort, SessionInvalidError
from linkedinbot.ports.secrets_provider_port import SecretsProviderPort


class SessionManager(LinkedInPort):
    def __init__(
        self,
        session: Session,
        secrets_provider: SecretsProviderPort,
        playwright_login: Callable[[], dict[str, Any]],
        session_validity_checker: Callable[[dict[str, Any]], bool],
        search_page: Callable[[dict[str, Any], str, str, int], list[str]],
    ) -> None:
        self._session = session
        self._secrets_provider = secrets_provider
        self._playwright_login = playwright_login
        self._session_validity_checker = session_validity_checker
        self._search_page = search_page

    def ensure_session(self, account_id: UUID) -> None:
        """M10.2 duzeltmesi (bagimsiz incelemede bulunan, gercek bir
        calistirmada ampirik olarak dogrulanmis bir bulgu): bu metod ONCEDEN
        yalnizca bir referansin VAR OLUP OLMADIGINI kontrol ediyordu -
        referansin GECERLI olup olmadigini DEGIL. Sonuc: bir hesabin oturumu
        LinkedIn tarafindan reddedilse bile, bu metod HICBIR ZAMAN yeniden
        interaktif giris tetiklemiyordu - `encrypted_storage_state_ref`in
        KENDISI hala mevcut oldugu icin erken donuyordu. Bu, manuel bir DB
        satiri silme/temizleme olmadan KENDI KENDINE asla iyilesemeyen,
        kalici bir kilitlenme durumuydu.

        Yeni davranis UC durumu ayirt eder:
        1. Hic kalici referans YOK -> interaktif giris (ONCEKI, degismemis
           yol).
        2. Referans VAR ve `session_status == EXPIRED` (`validate()`'in
           DAHA ONCE isaretledigi, ucuz/onbellekli bir sinyal) -> GEREKSIZ
           bir canli kontrol YAPMADAN dogrudan interaktif girise gecilir -
           zaten bilinen kotu bir oturumu tekrar canli kontrol etmek
           gereksiz bir ag cagrisidir.
        3. Referans VAR ve `session_status` EXPIRED DEGIL (orn. `VALID`
           veya hic dogrulanmamis) -> `validate()` (M3.2, AYNI
           `_session_validity_checker` callable'ini kullanarak) cagrilarak
           CANLI olarak kontrol edilir - bu, `session_status`in KENDISI
           stale/yanlis olabilecegi (orn. LinkedIn oturumu son
           dogrulamadan SONRA, DB HENUZ HABERDAR OLMADAN reddetmis olabilir
           - bu duzeltmenin dogrudan kanitladigi GERCEK senaryo) durumlar
           icin GEREKLIDIR. `validate()` basarili olursa (oturum HALA
           gecerli) bu metod hicbir sey yapmadan doner - insan mudahalesi
           GEREKMEZ. `validate()` `SessionInvalidError` firlatirsa,
           interaktif girise gecilir (asagidaki AYNI DB/secret guncelleme
           yolunu izleyerek).

        Her iki "interaktif girise gec" durumunda da sonuc AYNIDIR: yeni bir
        `storage_state` alinir ve KAYITLI referans/secret DEGISTIRILIR -
        yeni bir referans ADI ICAT EDILMEZ (ayni deterministik
        `linkedin_storage_state:{account_id}` anahtari yeni degerle UZERINE
        YAZILIR) - manuel bir DB temizligine ASLA gerek YOKTUR.
        """
        existing = self._session.get(LinkedInSessionOrm, account_id)
        has_reference = existing is not None and existing.encrypted_storage_state_ref is not None
        known_expired = has_reference and existing.session_status == SessionStatus.EXPIRED

        if has_reference and not known_expired:
            try:
                self.validate(account_id)
                return
            except SessionInvalidError:
                pass

        storage_state = self._playwright_login()
        secret_key = f"linkedin_storage_state:{account_id}"
        now = datetime.now(UTC)

        # SIRALAMA KASITLIDIR (bagimsiz incelemede bulunan Major bulgunun
        # duzeltmesi): DB yazimi (flush) Secrets Provider yazimindan ONCE
        # yapilir. Bu iki kalicilik mekanizmasi (SQL transaction'i ve
        # Secrets Provider'in kendi dosyasi) ortak bir transaction
        # PAYLASMAZ - biri digerini geri alamaz. Eger secret ONCE
        # yazilsaydi ve DB flush'i SONRA basarisiz olsaydı, kullanicinin
        # tamamladigi pahali bir interaktif giris (2FA/CAPTCHA dahil)
        # bosa gitmis olurdu: hicbir DB satirinin referans vermedigi
        # "yetim" bir secret diskte kalirdi. Bu sirayla, DB basarisizligi
        # secret yazimindan ONCE gerceklesir (hicbir yetim secret asla
        # olusmaz); DB basarili ama secret yazimi SONRADAN basarisiz
        # olursa da, cagiran (established `cli.seed()`/`_run_seed_command`
        # rollback konvansiyonuyla tutarli sekilde) transaction'i temiz
        # bicimde geri alabilir - hicbir tutarsiz ara durum kalmaz.
        if existing is not None:
            existing.encrypted_storage_state_ref = secret_key
            existing.session_status = SessionStatus.VALID
            existing.last_validated_at = now
        else:
            self._session.add(
                LinkedInSessionOrm(
                    account_id=account_id,
                    encrypted_storage_state_ref=secret_key,
                    session_status=SessionStatus.VALID,
                    last_validated_at=now,
                )
            )
        self._session.flush()

        self._secrets_provider.set(secret_key, json.dumps(storage_state))

    def validate(self, account_id: UUID) -> None:
        existing = self._session.get(LinkedInSessionOrm, account_id)
        if existing is None or existing.encrypted_storage_state_ref is None:
            raise SessionInvalidError(
                f"Hesap {account_id} icin kalici bir LinkedIn oturumu bulunamadi - "
                "once interaktif giris akisi (ensure_session, Roadmap M3.1) "
                "calistirilmalidir."
            )

        stored = self._secrets_provider.get(existing.encrypted_storage_state_ref)
        if stored is None:
            # Veri butunlugu tutarsizligi: DB bir referans tasiyor ama
            # Secrets Provider'da karsilik gelen deger yok. Normal
            # kullanimda olusmamasi gerekir (bkz. ensure_session()'in
            # DB-once/secret-sonra siralamasi), ama sessizce None'i
            # `json.loads()`'a verip anlamsiz bir TypeError firlatmak
            # yerine acikca SessionInvalidError'a donusturulur.
            raise SessionInvalidError(
                f"Hesap {account_id} icin DB'de bir oturum referansi var "
                f"({existing.encrypted_storage_state_ref}), ama Secrets Provider'da "
                "karsilik gelen bir deger bulunamadi."
            )

        storage_state = json.loads(stored)
        now = datetime.now(UTC)

        if self._session_validity_checker(storage_state):
            existing.session_status = SessionStatus.VALID
            existing.last_validated_at = now
            self._session.flush()
            return

        existing.session_status = SessionStatus.EXPIRED
        existing.last_validated_at = now
        self._session.flush()
        raise SessionInvalidError(
            f"Hesap {account_id} icin kayitli LinkedIn oturumu artik gecerli "
            "degil (LinkedIn oturumu kabul etmedi) - interaktif giris akisi "
            "(ensure_session, Roadmap M3.1) yeniden calistirilmalidir."
        )

    def search_jobs_page(
        self, account_id: UUID, location: str, keywords: str, page: int
    ) -> list[str]:
        # NOT: `validate()`'in "oturum yok/referans kirik" guvenlik agiyla
        # KASITLI OLARAK ayni sekilde tekrarlanir (bkz. modul dokumaninin
        # M3.3 notu) - `search_jobs_page()`'in kendi cagirani (PRD Workflow
        # adim 2->3 geregi Session Validation'dan SONRA calisan Collection)
        # `validate()`'i onceden cagirmis olsa BILE, bu metod kendi
        # basina guvenli olmalidir (orn. dogrudan/izole cagrilan bir
        # test veya gelecekteki bir hata durumu icin).
        existing = self._session.get(LinkedInSessionOrm, account_id)
        if existing is None or existing.encrypted_storage_state_ref is None:
            raise SessionInvalidError(
                f"Hesap {account_id} icin kalici bir LinkedIn oturumu bulunamadi - "
                "once interaktif giris akisi (ensure_session, Roadmap M3.1) "
                "calistirilmalidir."
            )

        # Bagimsiz incelemede bulunan bulgu: yalnizca referansin VAR
        # olmasina bakmak yeterli degildir - `validate()` (M3.2) bu
        # oturumu ONCEDEN EXPIRED olarak isaretlemis olabilir. Bu kontrol
        # olmadan, ARTIK GECERSIZ oldugu ZATEN BILINEN bir oturumla
        # gereksiz yere LinkedIn'e istek atilmis olurdu (session
        # consistency ihlali) - DB'nin kendi durumu yok sayilmamalidir.
        if existing.session_status == SessionStatus.EXPIRED:
            raise SessionInvalidError(
                f"Hesap {account_id} icin kayitli LinkedIn oturumu gecersiz "
                "olarak isaretli (session_status=EXPIRED) - interaktif giris "
                "akisi (ensure_session, Roadmap M3.1) yeniden calistirilmalidir."
            )

        stored = self._secrets_provider.get(existing.encrypted_storage_state_ref)
        if stored is None:
            raise SessionInvalidError(
                f"Hesap {account_id} icin DB'de bir oturum referansi var "
                f"({existing.encrypted_storage_state_ref}), ama Secrets Provider'da "
                "karsilik gelen bir deger bulunamadi."
            )

        storage_state = json.loads(stored)
        return self._search_page(storage_state, location, keywords, page)
