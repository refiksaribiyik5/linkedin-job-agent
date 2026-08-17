"""SessionManager icin entegrasyon testleri (Roadmap M3.1 + M3.2; Faz 13:
storage_state snapshot -> persistent Chromium profili mimari gecisi).

Roadmap M3.1 "Beklenen Sonuc": "Bir kez interaktif giris yapildiktan
sonra oturum kalici hale getirilir; surec yeniden baslatildiginda kimlik
bilgisi tekrar istenmez." Roadmap M3.2 "Beklenen Sonuc": "Gecersiz oturum
SessionInvalidError firlatir; genel bir crash degil, tanimli bir hata
turudur." Asagidaki testler bu davranislari (1) gercek bir DB satiri
(`linkedin_sessions`) uzerinden ve (2) sahte (in-memory) "interaktif
giris"/"oturum gecerlilik kontrolu" callable'lari + `tmp_path` altinda
disposable, GERCEK-OLMAYAN profil dizinleri uzerinden dogrular - gercek
Playwright'a bu dosyada hic dokunulmaz (bkz. test_playwright_client.py,
tarayici tarafi zaten ayri test edildi).

**Faz 13 mimari degisikligi (bu dosyanin kendisi icin onemli):**
`SessionManager` artik bir `SecretsProviderPort` almaz - kalici oturumun
KENDISI, hesap-bazli bir DIZIN (`profile_root/<account_id>/`) olarak
temsil edilir. "Kalici bir oturum var mi" sorusu artik bir DB-referans/
Secrets-Provider lookup'i DEGIL, dogrudan bir dosya-sistemi kontrolu
(`profile_dir.exists()`) ile cevaplanir. Bu yuzden bu dosyadaki sahte
callable'lar artik `dict` (storage_state) DEGIL, `Path` (profil dizini)
alir/doner - ONCEKI `_FakeSecretsProvider`/`json.dumps(...)` mekanizmasi
TAMAMEN kaldirildi (artik test edilecek bir sey yok - encrypted_storage_
state_ref DB sutunu KASITLI OLARAK legacy/kullanilmayan birakildi, bkz.
session_manager.py modul dokumani)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from linkedinbot.adapters.linkedin.session_manager import SessionManager
from linkedinbot.db.models import AccountOrm, LinkedInSessionOrm, SessionStatus
from linkedinbot.ports.linkedin_port import LinkedInPort, SessionInvalidError


@pytest.fixture
def profile_root(tmp_path: Path) -> Path:
    return tmp_path / "browser-profile"


@pytest.fixture
def playwright_login():
    calls: list[Path] = []

    def _login(user_data_dir: Path) -> None:
        calls.append(user_data_dir)
        # Gercek `perform_interactive_login()`'in kalici profili DISKE
        # YAZMASININ sahte karsiligi - `validate()`'in sonraki
        # `profile_dir.exists()` kontrolunun basarili GECEBILMESI icin
        # gereklidir (gercek Chromium burada YOKTUR).
        user_data_dir.mkdir(parents=True, exist_ok=True)

    _login.calls = calls
    return _login


@pytest.fixture
def session_validity_checker():
    calls: list[Path] = []
    state = {"return_value": True}

    def _check(user_data_dir: Path) -> bool:
        calls.append(user_data_dir)
        return state["return_value"]

    _check.calls = calls
    _check.state = state
    return _check


@pytest.fixture
def search_page():
    calls: list[tuple] = []
    state = {"return_value": []}

    def _search(user_data_dir: Path, location: str, keywords: str, page: int) -> list[str]:
        calls.append((user_data_dir, location, keywords, page))
        return state["return_value"]

    _search.calls = calls
    _search.state = state
    return _search


@pytest.fixture
def session_manager(
    db_session: Session,
    profile_root: Path,
    playwright_login,
    session_validity_checker,
    search_page,
) -> SessionManager:
    return SessionManager(
        db_session, profile_root, playwright_login, session_validity_checker, search_page
    )


def test_session_manager_implements_linkedin_port(session_manager: SessionManager):
    assert isinstance(session_manager, LinkedInPort)


def test_profile_dir_is_account_scoped(profile_root: Path, session_manager: SessionManager):
    # (Faz 13, madde 3 "Account Scoping"): iki farkli account_id ASLA ayni
    # dizini paylasamaz - gelecekte ikinci bir hesap eklense bile profil
    # cakismasi olusmamalidir (bkz. session_manager.py modul dokumaninin
    # "account_id parametresi olmadan hicbir Account-Scoped sorgu
    # calismaz" notu).
    from uuid import uuid4

    account_id_1 = uuid4()
    account_id_2 = uuid4()

    dir_1 = session_manager._profile_dir(account_id_1)
    dir_2 = session_manager._profile_dir(account_id_2)

    assert dir_1 != dir_2
    assert dir_1 == profile_root / str(account_id_1)
    assert dir_2 == profile_root / str(account_id_2)
    assert dir_1.parent == profile_root
    assert dir_2.parent == profile_root


def test_ensure_session_performs_login_when_no_existing_session(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    profile_root: Path,
    playwright_login,
):
    session_manager.ensure_session(account.account_id)

    expected_dir = profile_root / str(account.account_id)
    assert playwright_login.calls == [expected_dir]
    assert expected_dir.exists()

    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row is not None
    assert row.session_status == SessionStatus.VALID
    assert row.last_validated_at is not None
    # `encrypted_storage_state_ref` artik KASITLI OLARAK YAZILMAZ (legacy/
    # kullanilmayan alan, bkz. session_manager.py modul dokumani).
    assert row.encrypted_storage_state_ref is None


def test_ensure_session_skips_login_when_session_already_persisted_and_valid(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    profile_root: Path,
    playwright_login,
    session_validity_checker,
):
    # M10.2 duzeltmesi: "profil dizini var" TEK BASINA yeterli DEGILDIR
    # (bkz. ensure_session()'in kendi dokumani) - GERCEKTEN canli olarak
    # GECERLI olmasi gerekir.
    expected_dir = profile_root / str(account.account_id)
    expected_dir.mkdir(parents=True)
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref=None,
            session_status=SessionStatus.VALID,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()
    session_validity_checker.state["return_value"] = True

    session_manager.ensure_session(account.account_id)

    # Roadmap M3.1'in tam olarak istedigi sey: kimlik bilgisi TEKRAR
    # istenmez - interaktif giris callable'i hic cagirilmamali. Ama (M10.2)
    # bu, GERCEKTEN canli olarak dogrulanmis bir gecerlilige dayanmalidir -
    # checker'in cagirildigi da acikca dogrulanir.
    assert playwright_login.calls == []
    assert session_validity_checker.calls == [expected_dir]


def test_ensure_session_launches_login_when_session_marked_expired(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    profile_root: Path,
    playwright_login,
    session_validity_checker,
):
    # M10.2 duzeltmesi - EN ONEMLI senaryo: bu ONCEDEN sonsuza kadar
    # kilitlenen tam durumdu (bkz. ensure_session()'in kendi dokumani).
    # `session_status=EXPIRED` ONCEDEN bilindigi icin `validate()`'in
    # canli kontrolu HIC CAGRILMAZ (gereksiz bir ag istegi) - dogrudan
    # interaktif girise gecilir.
    expected_dir = profile_root / str(account.account_id)
    expected_dir.mkdir(parents=True)
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref=None,
            session_status=SessionStatus.EXPIRED,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    session_manager.ensure_session(account.account_id)

    assert playwright_login.calls == [expected_dir]
    # Zaten EXPIRED oldugu BILINEN bir oturum icin gereksiz bir canli
    # kontrol YAPILMAMALIDIR - verimlilik icin kasitli bir kisayol.
    assert session_validity_checker.calls == []
    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row.session_status == SessionStatus.VALID


def test_ensure_session_launches_login_and_replaces_session_when_validation_fails(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    profile_root: Path,
    playwright_login,
    session_validity_checker,
):
    # M10.2 duzeltmesi - `session_status` DB'de HALA `VALID` yaziyor olsa
    # bile (orn. LinkedIn oturumu son dogrulamadan SONRA, DB HENUZ
    # HABERDAR OLMADAN reddetmis olabilir), `validate()`'in canli kontrolu
    # bunu YAKALAR ve interaktif girise gecer.
    expected_dir = profile_root / str(account.account_id)
    expected_dir.mkdir(parents=True)
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref=None,
            session_status=SessionStatus.VALID,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()
    session_validity_checker.state["return_value"] = False

    session_manager.ensure_session(account.account_id)

    assert playwright_login.calls == [expected_dir]
    # Canli kontrol GERCEKTEN denendi (kisayol degil, M10.2'nin asil
    # kanitladigi senaryo).
    assert session_validity_checker.calls == [expected_dir]
    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row.session_status == SessionStatus.VALID


def test_ensure_session_updates_placeholder_row_missing_a_profile(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    profile_root: Path,
    playwright_login,
):
    # Bir hesap olusturulup ilk giris yapilmasi arasinda boyle bir "yer
    # tutucu" satir teorik olarak var olabilir (profil dizini DISKTE
    # HENUZ YOK). Bu durumda M3.1 hala giris yapip AYNI satiri
    # guncellemelidir (yeni bir satir eklemeye calisip PK ihlali
    # uretmemelidir).
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

    expected_dir = profile_root / str(account.account_id)
    assert playwright_login.calls == [expected_dir]
    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row.session_status == SessionStatus.VALID


def test_ensure_session_leaves_no_partial_db_state_when_login_fails(
    db_session: Session,
    account: AccountOrm,
    profile_root: Path,
    session_validity_checker,
    search_page,
):
    # Giris basarisiz olursa (orn. LoginTimeoutError - kullanici 2FA'yi
    # tamamlamadan vazgecti), hicbir DB satiri yazilmamalidir - basarisiz
    # bir girisin yarim/tutarsiz bir "oturum var" izlenimi birakmasi,
    # sonraki bir calistirmanin gecersiz/eksik bir profille calismaya
    # calismasina yol acardi.
    def _failing_login(user_data_dir: Path) -> None:
        raise RuntimeError("kullanici 2FA'yi tamamlamadan vazgecti")

    manager = SessionManager(
        db_session, profile_root, _failing_login, session_validity_checker, search_page
    )

    with pytest.raises(RuntimeError, match="2FA"):
        manager.ensure_session(account.account_id)

    assert db_session.get(LinkedInSessionOrm, account.account_id) is None


def test_ensure_session_propagates_db_flush_failure_without_partial_commit(
    db_session: Session,
    account: AccountOrm,
    profile_root: Path,
    playwright_login,
    session_validity_checker,
    search_page,
    monkeypatch,
):
    # Faz 13'te SecretsProvider kaldirildigi icin ("hangi sistem ONCE
    # yazilmali" sirasi - eski Major bulgu) artik geçerli bir senaryo
    # DEGIL: tek kalicilik mekanizmasi DB'nin kendisidir. Burada yalnizca
    # `flush()` basarisiz olursa hatanin duzgunce yukari sizdigi VE hicbir
    # yarim satirin commit EDILMEDIGI dogrulanir.
    manager = SessionManager(
        db_session, profile_root, playwright_login, session_validity_checker, search_page
    )

    original_flush = db_session.flush

    def _failing_flush(*args, **kwargs):
        if db_session.new or db_session.dirty:
            raise RuntimeError("simulated db failure")
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(db_session, "flush", _failing_flush)

    with pytest.raises(RuntimeError, match="simulated db failure"):
        manager.ensure_session(account.account_id)

    db_session.rollback()
    assert db_session.get(LinkedInSessionOrm, account.account_id) is None


# ---------------------------------------------------------------------------
# validate() (Roadmap M3.2, FR-1) - "Gecersiz/suresi dolmus oturumu sessizce
# yutmadan tespit etmek." Gecersiz bir oturum SessionInvalidError firlatir;
# genel bir crash degil, tanimli bir hata turudur.
# ---------------------------------------------------------------------------


def test_validate_raises_session_invalid_error_when_no_session_exists(
    session_manager: SessionManager,
    account: AccountOrm,
    session_validity_checker,
):
    # Hic giris yapilmamis (M3.1'in ensure_session'i hic calismamis) bir
    # hesap icin dogrulanacak hicbir sey yoktur - bu da "gecersiz oturum"
    # sayilir, sessizce yutulmaz.
    with pytest.raises(SessionInvalidError):
        session_manager.validate(account.account_id)

    assert session_validity_checker.calls == []


def test_validate_raises_session_invalid_error_when_profile_dir_missing(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    session_validity_checker,
):
    # DB satiri VAR ama profil dizini DISKTE YOK (orn. hic giris
    # yapilmamis bir "yer tutucu" satir, ya da profil manuel/kazayla
    # silinmis - bkz. Faz 13 recovery tasarimi). "profil mevcut mu"
    # kontrolu DB'nin kendi durumundan BAGIMSIZ olarak dosya sisteminden
    # yapilir.
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref=None,
            session_status=SessionStatus.UNKNOWN,
            last_validated_at=None,
        )
    )
    db_session.flush()

    with pytest.raises(SessionInvalidError):
        session_manager.validate(account.account_id)

    assert session_validity_checker.calls == []


def test_validate_passes_profile_dir_to_checker_and_succeeds_when_valid(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    profile_root: Path,
    session_validity_checker,
):
    expected_dir = profile_root / str(account.account_id)
    expected_dir.mkdir(parents=True)
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref=None,
            session_status=SessionStatus.UNKNOWN,
            last_validated_at=None,
        )
    )
    db_session.flush()
    session_validity_checker.state["return_value"] = True

    session_manager.validate(account.account_id)  # herhangi bir exception firlatmamali

    assert session_validity_checker.calls == [expected_dir]
    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row.session_status == SessionStatus.VALID
    assert row.last_validated_at is not None


def test_validate_raises_and_marks_expired_when_checker_reports_invalid(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    profile_root: Path,
    session_validity_checker,
):
    # Roadmap M3.2 "Tamamlanma Dogrulamasi"nin canli davranis karsiligi:
    # kayitli oturum gecersizlestirilmis (orn. LinkedIn cerezi sunucu
    # tarafinda sildi) gibi davranan bir checker - dogru hata turu
    # firlatilmali VE DB'nin session_status'u EXPIRED olarak
    # guncellenmelidir.
    (profile_root / str(account.account_id)).mkdir(parents=True)
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref=None,
            session_status=SessionStatus.VALID,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()
    session_validity_checker.state["return_value"] = False

    with pytest.raises(SessionInvalidError):
        session_manager.validate(account.account_id)

    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row.session_status == SessionStatus.EXPIRED
    assert row.last_validated_at is not None


def test_validate_does_not_reclassify_checker_errors_as_session_invalid(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    profile_root: Path,
):
    # Onemli ayrim (TDD Section 20: TransientError vs PermanentError): bir
    # ag/navigasyon hatasi (checker'in RuntimeError firlatmasi) "oturum
    # gecersiz" DEGILDIR. validate() bu hatayi SessionInvalidError'a
    # cevirmemeli/yutmamali VE satirin session_status'unu (yalnizca
    # checker GERCEKTEN False donduğunde EXPIRED'a cekilmesi gereken bir
    # alani) bir ag hatasi yuzunden yanlislikla degistirmemelidir.
    (profile_root / str(account.account_id)).mkdir(parents=True)
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref=None,
            session_status=SessionStatus.VALID,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    def _raising_checker(user_data_dir: Path):
        raise RuntimeError("simulated network failure")

    session_manager._session_validity_checker = _raising_checker

    with pytest.raises(RuntimeError, match="simulated network failure"):
        session_manager.validate(account.account_id)

    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row.session_status == SessionStatus.VALID


def test_validate_detects_manual_invalidation_of_a_previously_valid_session(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    session_validity_checker,
):
    # Roadmap M3.2 "Tamamlanma Dogrulamasi"nin tam metni: "Kayitli oturumu
    # manuel olarak gecersizlestirip dogrulamayi tekrar calistir; dogru
    # hata turunun firlatildigini dogrula." Once gercek bir giris
    # (ensure_session) yapilir, dogrulama basarili olur; sonra oturum
    # "gecersizlestirilir" (checker'in donus degeri degisir) ve validate()
    # TEKRAR calistirilir.
    session_manager.ensure_session(account.account_id)
    session_manager.validate(account.account_id)  # baslangicta hala gecerli

    session_validity_checker.state["return_value"] = False

    with pytest.raises(SessionInvalidError):
        session_manager.validate(account.account_id)

    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row.session_status == SessionStatus.EXPIRED


# ---------------------------------------------------------------------------
# search_jobs_page (Roadmap M3.3, FR-21) - `LinkedInPort`'un yeni soyut
# metodu: verilen (location, keywords, page) sorgusu icin, hesabin kalici
# oturumunu kullanarak TEK bir sayfalik ham ilan karti dizisini doner.
# ---------------------------------------------------------------------------


def test_search_jobs_page_raises_session_invalid_error_when_no_session_exists(
    session_manager: SessionManager,
    account: AccountOrm,
    search_page,
):
    with pytest.raises(SessionInvalidError):
        session_manager.search_jobs_page(account.account_id, "Istanbul", '"Sales"', 0)

    assert search_page.calls == []


def test_search_jobs_page_raises_session_invalid_error_when_profile_dir_missing(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    search_page,
):
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref=None,
            session_status=SessionStatus.UNKNOWN,
            last_validated_at=None,
        )
    )
    db_session.flush()

    with pytest.raises(SessionInvalidError):
        session_manager.search_jobs_page(account.account_id, "Istanbul", '"Sales"', 0)

    assert search_page.calls == []


def test_search_jobs_page_raises_session_invalid_error_when_session_marked_expired(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    profile_root: Path,
    search_page,
):
    # Bagimsiz incelemede bulunan bulgu: bir onceki validate() (M3.2)
    # cagrisi bu oturumu ZATEN EXPIRED olarak isaretlemis olabilir (bkz.
    # SessionManager.validate()). search_jobs_page() yalnizca profilin
    # VAR olup olmadigina bakip session_status'u yok sayarsa, ARTIK
    # GECERSIZ oldugu BILINEN bir oturumla gereksiz yere LinkedIn'e
    # istek atmaya calisir - bu, "session consistency" acisindan gercek
    # bir tutarsizliktir: DB'nin kendi durumu yok sayilmamalidir.
    (profile_root / str(account.account_id)).mkdir(parents=True)
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref=None,
            session_status=SessionStatus.EXPIRED,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    with pytest.raises(SessionInvalidError):
        session_manager.search_jobs_page(account.account_id, "Istanbul", '"Sales"', 0)

    assert search_page.calls == []


def test_search_jobs_page_delegates_to_injected_callable_with_profile_dir(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    profile_root: Path,
    search_page,
):
    expected_dir = profile_root / str(account.account_id)
    expected_dir.mkdir(parents=True)
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref=None,
            session_status=SessionStatus.VALID,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()
    search_page.state["return_value"] = ["<div>card</div>"]

    result = session_manager.search_jobs_page(account.account_id, "Istanbul", '"Sales"', 2)

    assert result == ["<div>card</div>"]
    assert search_page.calls == [(expected_dir, "Istanbul", '"Sales"', 2)]


def test_search_jobs_page_returns_empty_list_when_callable_returns_empty(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    profile_root: Path,
    search_page,
):
    (profile_root / str(account.account_id)).mkdir(parents=True)
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref=None,
            session_status=SessionStatus.VALID,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    assert session_manager.search_jobs_page(account.account_id, "Istanbul", '"Sales"', 0) == []
