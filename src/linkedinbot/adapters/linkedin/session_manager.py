"""SessionManager - `linkedin_port`'un implementasyonu (Roadmap M3.1: login
+ kaydetme; Roadmap M3.2: oturum dogrulama; Roadmap M3.3: arama sayfasi
getirme; Faz 13: storage_state snapshot -> persistent Chromium profili
mimari gecisi).

**Mimari degisiklik (Faz 13):** ONCEKI tasarim, kalici oturumu Secrets
Provider'da saklanan bir `storage_state` JSON anlik goruntusu olarak
tasiyordu - her dogrulama/toplama cagrisinda bu anlik goruntu SIFIRDAN
bos bir Playwright context'ine enjekte ediliyordu. M12'nin canli
dogrulamasinda kanitlandi ki bu "soguk yeniden oynatma" (cold replay)
deseni LinkedIn tarafindan guvenilmez bulunuyor (ayni storage_state hem
Docker'da hem HOST'ta, ayni ortamda dahi, YENIDEN olusturulmus bir
context'e yuklendiginde reddediliyor). Yeni tasarim, hesap-basina KALICI
bir Chromium profili (`<profile_root>/<account_id>/`, gercek native
Chromium `user_data_dir`) kullanir - giris VE dogrulama/toplama HER ZAMAN
AYNI profili acar/kapatir; hicbir "anlik goruntu cikar, baska yerde
yeniden olustur" adimi hic yasanmaz (bkz. playwright_client.py'nin kendi
"Mimari degisiklik" notu).

Bu sinif hala TDD Section 9'un tanimladigi ucu asamayi karsilar:

- `ensure_session()` (M3.1; M10.2 duzeltmesi: referans VARLIGI degil,
  GECERLILIGI kontrol edilir - bkz. metodun kendi dokumani): verilen hesap
  icin hesap-bazli profil dizini YOKSA (ya da `session_status=EXPIRED`
  olarak bilinen, ya da `validate()` canli kontrolunde basarisiz olan)
  `playwright_client.perform_interactive_login`'i (constructor'dan enjekte
  edilen bir callable olarak) tetikler, DB satirini gunceller/olusturur.
- `validate()` (M3.2, FR-1): kalici profilin HALA gecerli olup olmadigini,
  profil dizinini `playwright_client.check_session_is_valid`'e (yine
  enjekte edilen bir callable olarak) vererek canli kontrol eder.
  Gecersiz/eksik bir oturum sessizce yutulmaz - `SessionInvalidError`
  firlatilir; `session_status`/`last_validated_at` DB alanlari (TDD
  Section 15'in tam da bu amacla tanimladigi kolonlar) sonuca gore
  guncellenir - bu davranis DEGISMEDI.
- `search_jobs_page()` (M3.3, FR-21): profil dizinini
  `playwright_client.fetch_search_results_page`'e (yine enjekte edilen
  bir callable olarak) vererek TEK bir sayfalik ham ilan karti HTML'sini
  getirir. Sayfalama/limit MANTIGI burada YOKTUR - bu, `collection/collector.py`'nin
  (PaginationController) sorumlulugudur; bu metod yalnizca "kalici profili
  bul, tek sayfa getir" orkestrasyonunu yapar - `ensure_session()`/
  `validate()` ile AYNI "oturum yoksa SessionInvalidError" guvenlik agini
  paylasir.

**`encrypted_storage_state_ref` (DB, `linkedin_sessions`) artik BU
SINIF TARAFINDAN OKUNMAZ/YAZILMAZ** - eski mimarinin bir kalintisidir,
KASITLI OLARAK legacy/kullanilmayan birakilir (DB semasi/migration YOK -
proje talimatiyla acikca onaylandi). `session_status`/`last_validated_at`
DEGISMEDEN, ayni anlamla kullanilmaya devam eder. "Kalici bir oturum var
mi" sorusu artik bir DB-referans kontrolu DEGIL, dogrudan bir dosya-sistemi
kontrolu (`profile_dir.exists()`) ile cevaplanir - hesap-bazli profil
dizininin KENDISI, artik SecretsProvider'daki bir anahtarin YERINE gecen,
kalici oturum kanitidir.

DI deseni, kod tabaninin geri kalaniyla tutarlidir (bkz. cli.seed()):
`Session` ve `profile_root` (hesap-bazli DEGIL - `account_id`'ye gore
alt-dizin HER cagrida hesaplanir, bkz. `_profile_dir()`) constructor'dan
enjekte edilir (kendi kendine olusturulmaz); `account_id` ise
(repository'lerin `create()` metodlariyla ayni desende) HER cagriya
parametre olarak verilir, constructor'a gomulmez - TDD Section 14'un
"account_id parametresi olmadan hicbir Account-Scoped sorgu calismaz"
ilkesiyle tutarli (bu ayni zamanda profil dizinlerinin hesaplar arasinda
ASLA CAKISMAMASINI - account_id olmadan hicbir profil islemi yapilamaz -
yapisal olarak garanti eder). Bu sinif kendi basina COMMIT ETMEZ -
transaction sinirini cagiran yonetir (ayni `seed()` konvansiyonu).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from linkedinbot.db.models import LinkedInSessionOrm, SessionStatus
from linkedinbot.ports.linkedin_port import LinkedInPort, SessionInvalidError


def mark_session_valid(session: Session, account_id: UUID) -> None:
    """Basarili bir interaktif girisin (persistent profil hazir) DB
    bookkeeping'i - satiri (yoksa) olusturur / (varsa) gunceller,
    `session_status=VALID` + `last_validated_at=now()` yazar. `encrypted_
    storage_state_ref`'e HICBIR ZAMAN deger yazilmaz (legacy/kullanilmayan,
    bkz. modul dokumaninin kendi notu).

    Faz 13 regresyon duzeltmesi (bagimsiz incelemede bulunan bir bulgu):
    `cli.py::_run_login_command()`, kendi RunLock kapsamini KORUMAK icin
    (ikinci bir RunLock/SessionManager insa etmeden) `playwright_client.
    perform_interactive_login()`'i DOGRUDAN cagirir - `SessionManager.
    ensure_session()`'in TAMAMINI (kendi "profil varsa canli kontrol dene"
    kisa-yolu DAHIL) cagirmaz, cunku bu, kullanicinin ACIKCA istedigi
    interaktif giris adimini SESSIZCE atlayabilirdi (madde 6: "login" ile
    "validation" sorumluluklari KARISTIRILMAMALI). Ama bu, `ensure_session()`
    ile AYNI DB-yazma kuyrugunu (asagida) PAYLASMAZSA, `cli.py`'de basarili
    bir interaktif giris SONRASI hicbir DB satiri olusturulmuyordu -
    `validate()`'in kendi "existing is None -> SessionInvalidError" guvenlik
    agi (bkz. `validate()`'in kendi dokumani), hicbir DB satiri hic
    olusturulmamis YENI bir hesap icin, GERCEKTEN gecerli bir profili bile
    canli kontrol ETMEDEN reddediyordu - M10.2'nin duzelttigi "kendi kendine
    asla iyilesemeyen kalici kilitlenme" hata sinifinin FARKLI bir kod
    yolundan yeniden ortaya cikan hali. Bu fonksiyon, HER IKI cagiran
    (`ensure_session()` VE `cli.py::_run_login_command()`) tarafindan
    PAYLASILAN TEK DB-yazma yolu olarak bu ikilemi cozer - ikinci bir kopya
    mantik olusturulmaz.
    """
    existing = session.get(LinkedInSessionOrm, account_id)
    now = datetime.now(UTC)
    if existing is not None:
        existing.session_status = SessionStatus.VALID
        existing.last_validated_at = now
    else:
        session.add(
            LinkedInSessionOrm(
                account_id=account_id,
                encrypted_storage_state_ref=None,
                session_status=SessionStatus.VALID,
                last_validated_at=now,
            )
        )
    session.flush()


class SessionManager(LinkedInPort):
    def __init__(
        self,
        session: Session,
        profile_root: Path,
        playwright_login: Callable[[Path], None],
        session_validity_checker: Callable[[Path], bool],
        search_page: Callable[[Path, str, str, int], list[str]],
    ) -> None:
        self._session = session
        self._profile_root = profile_root
        self._playwright_login = playwright_login
        self._session_validity_checker = session_validity_checker
        self._search_page = search_page

    def _profile_dir(self, account_id: UUID) -> Path:
        """Hesap-bazli, DETERMINISTIK kalici Chromium profil yolu -
        `<profile_root>/<account_id>/`. DB'ye YAZILMAZ (bkz. modul
        dokumaninin "encrypted_storage_state_ref" notu) - `account_id`'den
        HER cagrida yeniden hesaplanir, bu yuzden iki farkli hesap ASLA
        ayni dizini paylasamaz."""
        return self._profile_root / str(account_id)

    def ensure_session(self, account_id: UUID) -> None:
        """M10.2 duzeltmesi (bagimsiz incelemede bulunan, gercek bir
        calistirmada ampirik olarak dogrulanmis bir bulgu): bu metod ONCEDEN
        yalnizca bir referansin VAR OLUP OLMADIGINI kontrol ediyordu -
        referansin GECERLI olup olmadigini DEGIL. Sonuc: bir hesabin oturumu
        LinkedIn tarafindan reddedilse bile, bu metod HICBIR ZAMAN yeniden
        interaktif giris tetiklemiyordu. Bu, manuel bir DB satiri silme/
        temizleme olmadan KENDI KENDINE asla iyilesemeyen, kalici bir
        kilitlenme durumuydu.

        Yeni davranis (Faz 13: profil-varligi, referans-varligi DEGIL) UC
        durumu ayirt eder:
        1. Hesap-bazli profil dizini YOK -> interaktif giris (ONCEKI,
           degismemis yol).
        2. Profil VAR ve `session_status == EXPIRED` (`validate()`'in
           DAHA ONCE isaretledigi, ucuz/onbellekli bir sinyal) -> GEREKSIZ
           bir canli kontrol YAPMADAN dogrudan interaktif girise gecilir -
           zaten bilinen kotu bir oturumu tekrar canli kontrol etmek
           gereksiz bir ag cagrisidir.
        3. Profil VAR ve `session_status` EXPIRED DEGIL (orn. `VALID`
           veya hic dogrulanmamis) -> `validate()` (M3.2, AYNI
           `_session_validity_checker` callable'ini kullanarak) cagrilarak
           CANLI olarak kontrol edilir - bu, `session_status`in KENDISI
           stale/yanlis olabilecegi (orn. LinkedIn oturumu son
           dogrulamadan SONRA, DB HENUZ HABERDAR OLMADAN reddetmis olabilir)
           durumlar icin GEREKLIDIR. `validate()` basarili olursa (oturum
           HALA gecerli) bu metod hicbir sey yapmadan doner - insan
           mudahalesi GEREKMEZ. `validate()` `SessionInvalidError`
           firlatirsa, interaktif girise gecilir (asagidaki AYNI DB
           guncelleme yolunu izleyerek).

        Her iki "interaktif girise gec" durumunda da sonuc AYNIDIR:
        `perform_interactive_login()` AYNI hesap-bazli profil dizinini
        (`_profile_dir(account_id)`) acar/gunceller - yeni bir dizin ADI
        ICAT EDILMEZ, profil KENDI ICINDE (Chromium'un native mekanizmasiyla)
        guncellenir; manuel bir DB temizligine ASLA gerek YOKTUR.
        """
        existing = self._session.get(LinkedInSessionOrm, account_id)
        profile_dir = self._profile_dir(account_id)
        has_profile = profile_dir.exists()
        known_expired = existing is not None and existing.session_status == SessionStatus.EXPIRED

        if has_profile and not known_expired:
            try:
                self.validate(account_id)
                return
            except SessionInvalidError:
                pass

        self._playwright_login(profile_dir)
        mark_session_valid(self._session, account_id)

    def validate(self, account_id: UUID) -> None:
        existing = self._session.get(LinkedInSessionOrm, account_id)
        profile_dir = self._profile_dir(account_id)
        if existing is None or not profile_dir.exists():
            raise SessionInvalidError(
                f"Hesap {account_id} icin kalici bir LinkedIn oturumu bulunamadi - "
                "once interaktif giris akisi (ensure_session, Roadmap M3.1) "
                "calistirilmalidir."
            )

        now = datetime.now(UTC)

        if self._session_validity_checker(profile_dir):
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
        # NOT: `validate()`'in "oturum yok/profil eksik" guvenlik agiyla
        # KASITLI OLARAK ayni sekilde tekrarlanir (bkz. modul dokumaninin
        # M3.3 notu) - `search_jobs_page()`'in kendi cagirani (PRD Workflow
        # adim 2->3 geregi Session Validation'dan SONRA calisan Collection)
        # `validate()`'i onceden cagirmis olsa BILE, bu metod kendi
        # basina guvenli olmalidir (orn. dogrudan/izole cagrilan bir
        # test veya gelecekteki bir hata durumu icin).
        existing = self._session.get(LinkedInSessionOrm, account_id)
        profile_dir = self._profile_dir(account_id)
        if existing is None or not profile_dir.exists():
            raise SessionInvalidError(
                f"Hesap {account_id} icin kalici bir LinkedIn oturumu bulunamadi - "
                "once interaktif giris akisi (ensure_session, Roadmap M3.1) "
                "calistirilmalidir."
            )

        # Bagimsiz incelemede bulunan bulgu: yalnizca profilin VAR
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

        return self._search_page(profile_dir, location, keywords, page)
