"""SessionManager icin entegrasyon testleri (Roadmap M3.1 + M3.2).

Roadmap M3.1 "Beklenen Sonuc": "Bir kez interaktif giris yapildiktan
sonra oturum storage_state olarak Secrets Provider uzerinden saklanir;
surec yeniden baslatildiginda kimlik bilgisi tekrar istenmez." Roadmap
M3.2 "Beklenen Sonuc": "Gecersiz oturum SessionInvalidError firlatir;
genel bir crash degil, tanimli bir hata turudur." Asagidaki testler bu
davranislari (1) gercek bir DB satiri (`linkedin_sessions`) uzerinden ve
(2) sahte (in-memory) bir SecretsProvider + sahte "interaktif giris"/
"oturum gecerlilik kontrolu" callable'lari uzerinden dogrular - gercek
Playwright'a bu dosyada hic dokunulmaz (bkz. test_playwright_client.py,
tarayici tarafi zaten ayri test edildi).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from linkedinbot.adapters.linkedin.session_manager import SessionManager
from linkedinbot.db.models import AccountOrm, LinkedInSessionOrm, SessionStatus
from linkedinbot.ports.linkedin_port import LinkedInPort, SessionInvalidError
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
def session_validity_checker():
    calls: list[dict] = []
    state = {"return_value": True}

    def _check(storage_state: dict) -> bool:
        calls.append(storage_state)
        return state["return_value"]

    _check.calls = calls
    _check.state = state
    return _check


@pytest.fixture
def search_page():
    calls: list[tuple] = []
    state = {"return_value": []}

    def _search(storage_state: dict, location: str, keywords: str, page: int) -> list[str]:
        calls.append((storage_state, location, keywords, page))
        return state["return_value"]

    _search.calls = calls
    _search.state = state
    return _search


@pytest.fixture
def session_manager(
    db_session: Session,
    secrets_provider: _FakeSecretsProvider,
    playwright_login,
    session_validity_checker,
    search_page,
) -> SessionManager:
    return SessionManager(
        db_session, secrets_provider, playwright_login, session_validity_checker, search_page
    )


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


def test_ensure_session_skips_login_when_session_already_persisted_and_valid(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    secrets_provider: _FakeSecretsProvider,
    playwright_login,
    session_validity_checker,
):
    # M10.2 duzeltmesi: "zaten bir referans var" TEK BASINA yeterli DEGILDIR
    # (bkz. ensure_session()'in kendi dokumani) - referansin GERCEKTEN
    # cozulebilir VE canli olarak GECERLI olmasi gerekir. Bu yuzden burada
    # (eski testin aksine) secrets_provider'a GERCEKTEN bir deger yazilir.
    secrets_provider.set("linkedin_storage_state:already-there", json.dumps(FAKE_STORAGE_STATE))
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref="linkedin_storage_state:already-there",
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
    assert session_validity_checker.calls == [FAKE_STORAGE_STATE]


def test_ensure_session_launches_login_when_session_marked_expired(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    secrets_provider: _FakeSecretsProvider,
    playwright_login,
    session_validity_checker,
):
    # M10.2 duzeltmesi - EN ONEMLI senaryo: bu ONCEDEN sonsuza kadar
    # kilitlenen tam durumdu (bkz. ensure_session()'in kendi dokumani).
    # `session_status=EXPIRED` ONCEDEN bilindigi icin `validate()`'in
    # canli kontrolu HIC CAGRILMAZ (gereksiz bir ag istegi) - dogrudan
    # interaktif girise gecilir.
    secrets_provider.set("linkedin_storage_state:stale", json.dumps(FAKE_STORAGE_STATE))
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref="linkedin_storage_state:stale",
            session_status=SessionStatus.EXPIRED,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    session_manager.ensure_session(account.account_id)

    assert len(playwright_login.calls) == 1
    # Zaten EXPIRED oldugu BILINEN bir oturum icin gereksiz bir canli
    # kontrol YAPILMAMALIDIR - verimlilik icin kasitli bir kisayol.
    assert session_validity_checker.calls == []
    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row.session_status == SessionStatus.VALID
    assert json.loads(secrets_provider.get(row.encrypted_storage_state_ref)) == FAKE_STORAGE_STATE


def test_ensure_session_launches_login_and_replaces_session_when_validation_fails(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    secrets_provider: _FakeSecretsProvider,
    playwright_login,
    session_validity_checker,
):
    # M10.2 duzeltmesi - `session_status` DB'de HALA `VALID` yaziyor olsa
    # bile (orn. LinkedIn oturumu son dogrulamadan SONRA, DB HENUZ
    # HABERDAR OLMADAN reddetmis olabilir - bu duzeltmenin dogrudan
    # kanitladigi GERCEK senaryo), `validate()`'in canli kontrolu bunu
    # YAKALAR ve interaktif girise gecer.
    old_ref = "linkedin_storage_state:old-and-rejected"
    secrets_provider.set(old_ref, json.dumps({"cookies": [{"name": "li_at", "value": "stale"}]}))
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref=old_ref,
            session_status=SessionStatus.VALID,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()
    session_validity_checker.state["return_value"] = False

    session_manager.ensure_session(account.account_id)

    assert len(playwright_login.calls) == 1
    # Canli kontrol GERCEKTEN denendi (kisayol degil, M10.2'nin asil
    # kanitladigi senaryo).
    assert session_validity_checker.calls == [{"cookies": [{"name": "li_at", "value": "stale"}]}]
    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row.session_status == SessionStatus.VALID
    assert row.encrypted_storage_state_ref is not None
    # Eski referans DEGIL, YENI girisin urettigi storage_state saklanmis
    # olmalidir - "degistirilir" gereksiniminin somut kaniti.
    assert json.loads(secrets_provider.get(row.encrypted_storage_state_ref)) == FAKE_STORAGE_STATE


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
    session_validity_checker,
    search_page,
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

    manager = SessionManager(
        db_session, secrets_provider, _failing_login, session_validity_checker, search_page
    )

    with pytest.raises(RuntimeError, match="2FA"):
        manager.ensure_session(account.account_id)

    assert db_session.get(LinkedInSessionOrm, account.account_id) is None
    assert secrets_provider._store == {}


def test_ensure_session_does_not_write_secret_if_db_write_fails(
    db_session: Session,
    account: AccountOrm,
    secrets_provider: _FakeSecretsProvider,
    playwright_login,
    session_validity_checker,
    search_page,
    monkeypatch,
):
    # Bagimsiz incelemede bulunan Major bulgu: DB yazimi (flush) ile
    # Secrets Provider yazimi birbirinden bagimsiz iki kalicilik
    # mekanizmasidir - hicbir ortak transaction'lari yoktur. Eger secret
    # ONCE yazilirsa ve DB flush'i SONRA basarisiz olursa, kullanicinin
    # tamamladigi pahali bir interaktif giris (2FA/CAPTCHA dahil) bosa
    # gitmis olur: disk uzerinde hicbir DB satirinin referans vermedigi,
    # "yetim" bir secret kalir. Duzeltme: DB yazimi (flush) SIRAYLA ONCE
    # yapilir; yalnizca basarili olursa secret yazilir - boylece DB
    # basarisizligi secret yazimindan ONCE gerceklesir, hicbir yetim
    # secret asla olusmaz.
    manager = SessionManager(
        db_session, secrets_provider, playwright_login, session_validity_checker, search_page
    )

    # NOT: `session.get(...)` kendi ici SQLAlchemy autoflush'i tetikler -
    # bu, bekleyen HICBIR degisiklik olmadiginda bile `flush()`'i cagirir
    # (zararsiz bir no-op olarak). Kosulsuz bir "her zaman patla" sahte
    # flush, bu zararsiz autoflush cagrisini da yakalayip testi YANLIS
    # noktada (henuz playwright_login/secrets.set'e hic ulasmadan)
    # patlatirdi - bu yuzden yalnizca GERCEKTEN bekleyen (yeni/degismis)
    # nesne varken basarisiz olan bir sarmalayici kullanilir.
    original_flush = db_session.flush

    def _failing_flush(*args, **kwargs):
        if db_session.new or db_session.dirty:
            raise RuntimeError("simulated db failure")
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(db_session, "flush", _failing_flush)

    with pytest.raises(RuntimeError, match="simulated db failure"):
        manager.ensure_session(account.account_id)

    assert secrets_provider._store == {}


def test_ensure_session_db_row_is_cleanly_rollback_recoverable_if_secret_write_fails(
    db_session: Session,
    account: AccountOrm,
    playwright_login,
    session_validity_checker,
    search_page,
):
    # Ayni bulgunun diger yarisi: DB yazimi ONCE gerceklestigi icin,
    # SONRASINDA secret yazimi basarisiz olursa (orn. disk dolu), cagiran
    # (established `cli.seed()`/`_run_seed_command` konvansiyonuyla
    # tutarli sekilde) transaction'i geri alabilir (rollback) ve hicbir
    # tutarsiz/yarim durum kalmaz - ne "DB'de var ama secret'i yok" bir
    # satir, ne de bir yetim secret.
    # `account.account_id` rollback ONCESINDE yakalanir: `db_session.rollback()`
    # bu session'daki TUM nesneleri (henuz commit edilmemis `account` dahil)
    # expire eder; rollback SONRASI `account.account_id`'ye tekrar erismeye
    # calismak, artik var olmayan satiri yeniden yuklemeye calisip
    # `ObjectDeletedError` firlatirdi.
    account_id = account.account_id

    class _FailingSecretsProvider(SecretsProviderPort):
        def get(self, key: str) -> str | None:
            return None

        def set(self, key: str, value: str) -> None:
            raise RuntimeError("disk full")

    manager = SessionManager(
        db_session,
        _FailingSecretsProvider(),
        playwright_login,
        session_validity_checker,
        search_page,
    )

    with pytest.raises(RuntimeError, match="disk full"):
        manager.ensure_session(account_id)

    db_session.rollback()

    assert db_session.get(LinkedInSessionOrm, account_id) is None


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


def test_validate_raises_session_invalid_error_when_ref_is_null(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    session_validity_checker,
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
        session_manager.validate(account.account_id)

    assert session_validity_checker.calls == []


def test_validate_raises_session_invalid_error_when_secret_missing_for_ref(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    session_validity_checker,
):
    # Veri butunlugu tutarsizligi (normal kullanimda olusmamasi gereken,
    # ama savunmaci sekilde ele alinmasi gereken bir durum): DB'de bir
    # referans var ama Secrets Provider'da karsilik gelen bir deger yok.
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref="linkedin_storage_state:missing",
            session_status=SessionStatus.VALID,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    with pytest.raises(SessionInvalidError):
        session_manager.validate(account.account_id)

    assert session_validity_checker.calls == []


def test_validate_passes_stored_storage_state_to_checker_and_succeeds_when_valid(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    secrets_provider: _FakeSecretsProvider,
    session_validity_checker,
):
    secrets_provider.set("linkedin_storage_state:existing", json.dumps(FAKE_STORAGE_STATE))
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref="linkedin_storage_state:existing",
            session_status=SessionStatus.UNKNOWN,
            last_validated_at=None,
        )
    )
    db_session.flush()
    session_validity_checker.state["return_value"] = True

    session_manager.validate(account.account_id)  # herhangi bir exception firlatmamali

    assert session_validity_checker.calls == [FAKE_STORAGE_STATE]
    row = db_session.get(LinkedInSessionOrm, account.account_id)
    assert row.session_status == SessionStatus.VALID
    assert row.last_validated_at is not None


def test_validate_raises_and_marks_expired_when_checker_reports_invalid(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    secrets_provider: _FakeSecretsProvider,
    session_validity_checker,
):
    # Roadmap M3.2 "Tamamlanma Dogrulamasi"nin canli davranis karsiligi:
    # kayitli oturum gecersizlestirilmis (orn. bir cerez silinmis) gibi
    # davranan bir checker - dogru hata turu firlatilmali VE DB'nin
    # session_status'u EXPIRED olarak guncellenmelidir (bu alanlarin
    # TDD Section 15'teki tam da bu amac icin var oldugu sema).
    secrets_provider.set("linkedin_storage_state:existing", json.dumps(FAKE_STORAGE_STATE))
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref="linkedin_storage_state:existing",
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
    secrets_provider: _FakeSecretsProvider,
):
    # Onemli ayrim (TDD Section 20: TransientError vs PermanentError): bir
    # ag/navigasyon hatasi (checker'in RuntimeError firlatmasi) "oturum
    # gecersiz" DEGILDIR. validate() bu hatayi SessionInvalidError'a
    # cevirmemeli/yutmamali VE satirin session_status'unu (yalnizca
    # checker GERCEKTEN False donduğunde EXPIRED'a cekilmesi gereken bir
    # alani) bir ag hatasi yuzunden yanlislikla degistirmemelidir.
    secrets_provider.set("linkedin_storage_state:existing", json.dumps(FAKE_STORAGE_STATE))
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref="linkedin_storage_state:existing",
            session_status=SessionStatus.VALID,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    def _raising_checker(storage_state):
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
    # manuel olarak gecersizlestirip (orn. cerezi silerek) dogrulamayi
    # tekrar calistir; dogru hata turunun firlatildigini dogrula." Once
    # gercek bir giris (ensure_session) yapilir, dogrulama basarili olur;
    # sonra oturum "gecersizlestirilir" (checker'in donus degeri degisir,
    # cerez silme'nin canli davranis karsiligi) ve validate() TEKRAR
    # calistirilir.
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
# `collection/collector.py`'nin (M3.3) `linkedin_port`'a bagimli olmasi
# gerektigi kararinin (proje talimatiyla acikca onaylandi) somut karsiligi.
# ---------------------------------------------------------------------------


def test_search_jobs_page_raises_session_invalid_error_when_no_session_exists(
    session_manager: SessionManager,
    account: AccountOrm,
    search_page,
):
    with pytest.raises(SessionInvalidError):
        session_manager.search_jobs_page(account.account_id, "Istanbul", '"Sales"', 0)

    assert search_page.calls == []


def test_search_jobs_page_raises_session_invalid_error_when_ref_is_null(
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
    secrets_provider: _FakeSecretsProvider,
    search_page,
):
    # Bagimsiz incelemede bulunan bulgu: bir onceki validate() (M3.2)
    # cagrisi bu oturumu ZATEN EXPIRED olarak isaretlemis olabilir (bkz.
    # SessionManager.validate()). search_jobs_page() yalnizca referansin
    # VAR olup olmadigina bakip session_status'u yok sayarsa, ARTIK
    # GECERSIZ oldugu BILINEN bir oturumla gereksiz yere LinkedIn'e
    # istek atmaya calisir - bu, "session consistency" acisindan gercek
    # bir tutarsizliktir: DB'nin kendi durumu yok sayilir.
    secrets_provider.set("linkedin_storage_state:existing", json.dumps(FAKE_STORAGE_STATE))
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref="linkedin_storage_state:existing",
            session_status=SessionStatus.EXPIRED,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    with pytest.raises(SessionInvalidError):
        session_manager.search_jobs_page(account.account_id, "Istanbul", '"Sales"', 0)

    assert search_page.calls == []


def test_search_jobs_page_raises_session_invalid_error_when_secret_missing_for_ref(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    search_page,
):
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref="linkedin_storage_state:missing",
            session_status=SessionStatus.VALID,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    with pytest.raises(SessionInvalidError):
        session_manager.search_jobs_page(account.account_id, "Istanbul", '"Sales"', 0)

    assert search_page.calls == []


def test_search_jobs_page_delegates_to_injected_callable_with_stored_storage_state(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    secrets_provider: _FakeSecretsProvider,
    search_page,
):
    secrets_provider.set("linkedin_storage_state:existing", json.dumps(FAKE_STORAGE_STATE))
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref="linkedin_storage_state:existing",
            session_status=SessionStatus.VALID,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()
    search_page.state["return_value"] = ["<div>card</div>"]

    result = session_manager.search_jobs_page(account.account_id, "Istanbul", '"Sales"', 2)

    assert result == ["<div>card</div>"]
    assert search_page.calls == [(FAKE_STORAGE_STATE, "Istanbul", '"Sales"', 2)]


def test_search_jobs_page_returns_empty_list_when_callable_returns_empty(
    db_session: Session,
    account: AccountOrm,
    session_manager: SessionManager,
    secrets_provider: _FakeSecretsProvider,
    search_page,
):
    secrets_provider.set("linkedin_storage_state:existing", json.dumps(FAKE_STORAGE_STATE))
    db_session.add(
        LinkedInSessionOrm(
            account_id=account.account_id,
            encrypted_storage_state_ref="linkedin_storage_state:existing",
            session_status=SessionStatus.VALID,
            last_validated_at=datetime.now(UTC),
        )
    )
    db_session.flush()

    assert session_manager.search_jobs_page(account.account_id, "Istanbul", '"Sales"', 0) == []
