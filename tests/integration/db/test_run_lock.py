"""RunLock icin entegrasyon testleri (Roadmap M9.1, FR-12, TDD Section
14/17, v1.1 Fix 5).

Roadmap M9.1 "Amac": "FR-12'nin cakisma onleme garantisini,
`lock_expires_at` zaman asimi dahil (TDD v1.1 Fix 5) uygulamak."
"Beklenen Sonuc": "Ikinci bir eszamanli calistirma reddedilir; suresi
dolmus bir kilit otomatik olarak gecersiz sayilir." "Tamamlanma
Dogrulamasi": "Kilidi al, ikinci alim denemesinin reddedildigini
dogrula; `lock_expires_at`'i gecmise ayarlayip ucuncu denemenin basarili
oldugunu dogrula."

Bu modul GERCEK bir DB oturumuna karsi test eder (tmp fixture DEGIL,
`tests/integration/db/conftest.py`'nin paylasilan `db_session`/`account`
fixture'lari) - RunLock'un TUM amaci, eszamanli erisimde DOGRU
davranmaktir; bu, yalnizca gercek DB'nin atomik `INSERT ... ON CONFLICT
... WHERE ... RETURNING` garantisiyle anlamli sekilde test edilebilir
(bkz. `run/run_lock.py` modul dokumani - bu tasarim karari, uygulamadan
once REPL'de ampirik olarak dogrulanmistir).

Mimari not: `run/run_lock.py`, M1.3'un `ports/*_repository_port.py`
deseninin AKSINE bir Port arayuzu TANIMLAMAZ - Roadmap M9.1'in kendi
"Olusturulacak Dosyalar" listesi YALNIZCA `run/run_lock.py`'yi sayar (M1.3
"Olusturulacak Dosyalar" listesinde run_lock icin bir port/repository
YOKTUR - kasitli bir dislama, cunku run_locks generic bir CRUD varligi
degil, tamamen DB'nin kendi atomiklik garantilerine baglantili ozel bir
mutex mekanizmasidir). Bu yuzden `RunLock`, diger repository'ler
(`SqlAlchemyReportRepository` vb.) ile AYNI "constructor'dan Session al"
desenini izler, ama bir Port'u UYGULAMAZ.

`lock_owner` VE `lock_duration` (ve `now`), DOGRUDAN cagirana birakilan
duz parametrelerdir - M8.1/M8.2'nin `top_n`/`is_bootstrap` deseniyle AYNI
ilkeyi izler (NFR-6/Config-Is Mantigi Ayrimi): PRD Section 17'nin
konfigurasyon tablosunda bir "Lock Timeout" parametresi ACIKCA
LISTELENMEZ, bu yuzden somut bir varsayilan deger `run_lock.py`'ye
GOMULMEZ - gelecekteki orkestrasyon katmani (M9.2) bu degeri (config'ten
veya sabit bir sabitten) kendisi saglar. `lock_owner`'in NE anlama
geldigine (process ID, run ID, vb.) `run_lock.py` KARAR VERMEZ - opak bir
string olarak saklanir/karsilastirilir.

`release()`'in `lock_owner` ESLESMESI GEREKTIRMESI (kasitli tasarim
karari, escalasyon gerektirmeyen dogal sonuc): `lock_expires_at` zaman
asimi mekanizmasi (TDD Section 17/EDGE-14) geregi, bir kilit
SAHIBI zaman icinde DEGISEBILIR (surec A'nin kilidi suresi dolar, surec
B kiliti alir, sonra surec A'nin GEC gelen/cokme-sonrasi temizlik kodu
release() cagirir) - eger release() sahiplik KONTROLU yapmasaydi, surec
A yanlislikla surec B'nin GECERLI kilidini SILERDI. `lock_owner`
sutununun VAR OLMASI (yalnizca bilgilendirici degil) bu dogrulamanin
Section 15'in kendi semasi tarafindan ONGORULDUGUNU gosterir.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from linkedinbot.db.models import AccountOrm, RunLockOrm
from linkedinbot.run.run_lock import RunLock

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
ONE_HOUR = timedelta(hours=1)


def _get_lock_row(db_session: Session, account_id) -> RunLockOrm | None:
    return db_session.get(RunLockOrm, account_id)


def test_acquire_succeeds_when_no_lock_row_exists_yet(db_session: Session, account: AccountOrm):
    lock = RunLock(db_session)

    acquired = lock.acquire(account.account_id, "owner-A", NOW, ONE_HOUR)

    assert acquired is True
    row = _get_lock_row(db_session, account.account_id)
    assert row is not None
    assert row.locked_at == NOW
    assert row.lock_owner == "owner-A"
    assert row.lock_expires_at == NOW + ONE_HOUR


def test_second_acquire_is_rejected_while_the_lock_is_still_valid(
    db_session: Session, account: AccountOrm
):
    # Roadmap M9.1 Tamamlanma Dogrulamasi: "Kilidi al, ikinci alim
    # denemesinin reddedildigini dogrula."
    lock = RunLock(db_session)
    assert lock.acquire(account.account_id, "owner-A", NOW, ONE_HOUR) is True

    rejected = lock.acquire(account.account_id, "owner-B", NOW + timedelta(minutes=30), ONE_HOUR)

    assert rejected is False
    row = _get_lock_row(db_session, account.account_id)
    assert row.lock_owner == "owner-A"


def test_acquire_succeeds_after_the_lock_has_expired(db_session: Session, account: AccountOrm):
    # Roadmap M9.1 Tamamlanma Dogrulamasi: "`lock_expires_at`'i gecmise
    # ayarlayip ucuncu denemenin basarili oldugunu dogrula."
    lock = RunLock(db_session)
    assert lock.acquire(account.account_id, "owner-A", NOW, ONE_HOUR) is True
    rejected = lock.acquire(account.account_id, "owner-B", NOW + timedelta(minutes=30), ONE_HOUR)
    assert rejected is False

    past_expiry_now = NOW + timedelta(hours=2)
    acquired = lock.acquire(account.account_id, "owner-C", past_expiry_now, ONE_HOUR)

    assert acquired is True
    row = _get_lock_row(db_session, account.account_id)
    assert row.lock_owner == "owner-C"
    assert row.locked_at == past_expiry_now
    assert row.lock_expires_at == past_expiry_now + ONE_HOUR


def test_acquire_succeeds_exactly_at_the_expiry_boundary(db_session: Session, account: AccountOrm):
    # Sinir durumu: `lock_expires_at < now` (kesin esitlik DEGIL, kucuktur)
    # - kilit "simdi" tam olarak sona erdigi anda hala GECERLI sayilir mi
    # yoksa gecersiz mi? `run_lock.py`'nin kendi tasarim karari: `now ==
    # lock_expires_at` HENUZ suresi dolmamis sayilir (kesin sinirda
    # "guvenli taraf" - kilit sahibine bir sonraki tick'e kadar tam
    # sureyi tanir), bu yuzden bu ANDA bir rakip acquire REDDEDILIR.
    lock = RunLock(db_session)
    assert lock.acquire(account.account_id, "owner-A", NOW, ONE_HOUR) is True

    exactly_at_expiry = NOW + ONE_HOUR
    rejected = lock.acquire(account.account_id, "owner-B", exactly_at_expiry, ONE_HOUR)

    assert rejected is False


def test_release_clears_the_lock_when_the_owner_matches(db_session: Session, account: AccountOrm):
    lock = RunLock(db_session)
    lock.acquire(account.account_id, "owner-A", NOW, ONE_HOUR)

    released = lock.release(account.account_id, "owner-A")

    assert released is True
    row = _get_lock_row(db_session, account.account_id)
    assert row.locked_at is None
    assert row.lock_owner is None
    assert row.lock_expires_at is None


def test_release_is_a_noop_when_the_owner_does_not_match(db_session: Session, account: AccountOrm):
    # Kritik guvenlik ozelligi: suresi dolmus bir kilidin ESKI sahibi
    # (gec gelen/cokme-sonrasi temizlik kodu), o arada baska bir surecin
    # ALDIGI YENI, GECERLI kilidi yanlislikla SILEMEZ.
    lock = RunLock(db_session)
    lock.acquire(account.account_id, "owner-A", NOW, ONE_HOUR)
    lock.acquire(account.account_id, "owner-B", NOW + timedelta(hours=2), ONE_HOUR)

    released = lock.release(account.account_id, "owner-A")

    assert released is False
    row = _get_lock_row(db_session, account.account_id)
    assert row.lock_owner == "owner-B"
    assert row.locked_at is not None


def test_release_is_a_noop_when_no_lock_row_exists(db_session: Session, account: AccountOrm):
    lock = RunLock(db_session)

    released = lock.release(account.account_id, "owner-A")

    assert released is False
    assert _get_lock_row(db_session, account.account_id) is None


def test_release_is_a_noop_when_the_lock_is_already_released(
    db_session: Session, account: AccountOrm
):
    lock = RunLock(db_session)
    lock.acquire(account.account_id, "owner-A", NOW, ONE_HOUR)
    assert lock.release(account.account_id, "owner-A") is True

    released_again = lock.release(account.account_id, "owner-A")

    assert released_again is False


def test_locks_are_isolated_per_account(db_session: Session, account: AccountOrm):
    other_account = AccountOrm(display_name="Other", created_at=NOW, status="active")
    db_session.add(other_account)
    db_session.flush()
    lock = RunLock(db_session)

    assert lock.acquire(account.account_id, "owner-A", NOW, ONE_HOUR) is True
    # Farkli bir hesap icin ayni anda acquire etmek, ILK hesabin kilidinden
    # HICBIR SEKILDE etkilenmemelidir.
    assert lock.acquire(other_account.account_id, "owner-B", NOW, ONE_HOUR) is True

    assert lock.release(account.account_id, "owner-A") is True
    # Bir hesabin kilidini serbest birakmak, DIGER hesabin kilidini
    # ETKILEMEMELIDIR.
    row = _get_lock_row(db_session, other_account.account_id)
    assert row.lock_owner == "owner-B"


def test_lock_state_is_not_stale_after_release_and_reacquire_in_the_same_session(
    db_session: Session, account: AccountOrm
):
    # Self-review bulgusu: `acquire()`/`release()` Core-duzeyinde ifadeler
    # (ORM'un normal nesne-izlemesini ATLAYAN `INSERT ... ON CONFLICT` /
    # `UPDATE ... RETURNING`) kullanir. Eger cagiran, AYNI oturumda daha
    # ONCE `session.get(RunLockOrm, ...)` ile bu satiri sorgulamissa,
    # SQLAlchemy'nin identity map'i o nesneyi ONBELLEKLER; sonraki bir
    # `acquire()`/`release()` cagirisindan SONRA yapilan IKINCI bir
    # `session.get()` cagirisi, DB'ye GITMEDEN AYNI (artik BAYAT) Python
    # nesnesini dondurebilir - somut olarak yeniden uretildi (REPL'de
    # `row1 is row2 == True` ve `row2.lock_owner` DB'deki gercek degeri
    # DEGIL, eski degeri gosteriyordu).
    lock = RunLock(db_session)
    now = NOW

    lock.acquire(account.account_id, "owner-A", now, ONE_HOUR)
    # Bu satiri identity map'e ONBELLEKLETMEK icin BILEREK erken bir
    # session.get() cagirisi yapilir.
    first_read = _get_lock_row(db_session, account.account_id)
    assert first_read.lock_owner == "owner-A"

    lock.release(account.account_id, "owner-A")
    lock.acquire(account.account_id, "owner-C", now + timedelta(hours=2), ONE_HOUR)

    second_read = _get_lock_row(db_session, account.account_id)
    assert second_read.lock_owner == "owner-C"


def test_run_lock_does_not_implement_a_port_abstraction():
    # Mimari not (bkz. modul dokumani): Roadmap M9.1'in kendi
    # "Olusturulacak Dosyalar" listesi YALNIZCA `run/run_lock.py`'yi
    # sayar - kasitli olarak bir Port/Repository katmani YOKTUR. Bu test,
    # gelecekte yanlislikla bir Port eklenip eklenmedigini DEGIL, `RunLock`
    # sinifinin dogrudan `Session` alan basit bir sinif olarak KALDIGINI
    # dokumante eder.
    import inspect

    assert inspect.isclass(RunLock)
    signature = inspect.signature(RunLock.__init__)
    assert list(signature.parameters) == ["self", "session"]
