"""RunLock - FR-12'nin cakisma onleme garantisi (Roadmap M9.1, TDD
Section 14/17, v1.1 Fix 5).

**Neden bir Port/Repository katmani YOK (kasitli, Roadmap'ten dogrudan
okunan bir karar):** Roadmap M9.1'in kendi "Oluşturulacak Dosyalar"
listesi YALNIZCA `run/run_lock.py`'yi sayar (M8.3'un `ports/
report_store_port.py` + `adapters/reporting/filesystem_report_store.py`
IKILISININ aksine). M1.3'un kendi "Oluşturulacak Dosyalar" listesi de
(altı repository) `run_lock` icin bir port/repository TANIMLAMAZ - bu
kasitli bir dislamadir: `run_locks`, diger Account-Scoped tablolar gibi
generic bir CRUD varligi degildir, DB'nin KENDI atomiklik garantisine
(tek bir `INSERT ... ON CONFLICT ... WHERE ... RETURNING` ifadesi)
DOGRUDAN baglidir - bu yuzden `RunLock`, diger repository siniflarinin
("constructor'dan `Session` al") AYNI desenini izler, ama bir Port'u
UYGULAMAZ (import-linter kontratlari `linkedinbot.run`'a boyle bir
kisitlama getirmez - yalnizca `linkedinbot.domain`/`linkedinbot.ports`
kisitlidir).

**Atomiklik tasarimi (uygulamadan once REPL'de ampirik olarak
dogrulanmistir):** `acquire()`, TEK bir `INSERT ... ON CONFLICT
(account_id) DO UPDATE ... WHERE ... RETURNING account_id` ifadesi
kullanir - bu, "satir hic yoksa ekle (her zaman basarili) VEYA satir
VARSA yalnizca kilitsizse/suresi dolmussa guncelle" mantigini TEK, atomik
bir veritabani round-trip'inde birlestirir. Bu, ONCE `SELECT` ile
kontrol edip SONRA `INSERT`/`UPDATE` yapan (M8.3'un ilk `save()`
uygulamasinda bulunan TOCTOU hatasiyla AYNI SINIF bir hataya acik olacak)
bir "check-then-act" deseninden BILINCLI OLARAK kacinir - RunLock'un
BUTUN amaci tam da bu es zamanlilik senaryosunda dogru davranmaktir,
bu yuzden kendisinin atomik olmayan bir kontrol deseni tasimasi kabul
edilemezdi.

**`lock_owner`/`now`/`lock_duration` neden dogrudan parametre (escalasyon
gerektirmeyen dogal sonuc):** PRD Section 17'nin konfigurasyon
tablosunda bir "Lock Timeout" parametresi ACIKCA LISTELENMEZ - bu yuzden
somut bir sure sabiti bu modulde GOMULMEZ; M8.1'in `top_n`'i / M8.2'nin
`is_bootstrap`'i ile AYNI ilkeyi izleyerek, cagirana (gelecekteki M9.2
Orchestrator) birakilir. `lock_owner`'in ANLAMINA (process ID, run ID
vb.) bu modul KARAR VERMEZ - opak bir string olarak saklanir/karsilastirilir.

**`release()` neden sahiplik (owner) eslesmesi ister:** `lock_expires_at`
zaman asimi mekanizmasi (TDD Section 17/EDGE-14) geregi bir kilidin
SAHIBI zaman icinde DEGISEBILIR (surec A'nin kilidi suresi dolar, surec
B kiliti alir, sonra surec A'nin GEC gelen/cokme-sonrasi temizlik kodu
`release()` cagirir). Sahiplik kontrolu OLMASAYDI, surec A yanlislikla
surec B'nin GECERLI kilidini SILERDI. `run_locks.lock_owner` sutununun
VAR OLMASI (yalnizca bilgilendirici degil) bu dogrulamanin semanin
kendisi tarafindan ONGORULDUGUNU gosterir.

**Duzeltme notu (self-review bulgusu): hedefli `expire()`, neden
`expire_all()` DEGIL.** `acquire()`/`release()`, ORM'un normal nesne
izlemesini ATLAYAN Core-duzeyinde ifadeler (`INSERT ... ON CONFLICT` /
`UPDATE ... RETURNING`) kullanir. Cagiran, AYNI oturumda bu satiri daha
ONCE `session.get(RunLockOrm, ...)` ile sorgulamissa, SQLAlchemy'nin
identity map'i o nesneyi onbellekler; bu Core ifadeleri o onbellegi
GUNCELLEMEZ - sonraki bir `session.get()` cagirisi DB'ye gitmeden AYNI
(artik bayat) nesneyi dondurebilir (somut olarak yeniden uretildi).
Ilk dusunulen duzeltme `Session.expire_all()` idi, ama bu, AYNI oturumda
BASKA, ILGISIZ nesnelere ait HENUZ flush edilmemis (pending) degisiklikleri
de SESSIZCE ATAR (ampirik olarak dogrulandi) - NFR-13/TDD Section 17'nin
"tek transaction'da commit edilecek veriler" stratejisi geregi, RunLock
tipik olarak `evaluated_jobs`/`reports`/`run_logs` icin COK sayida
flush-edilmemis degisiklik tasiyan AYNI oturumdan cagrilacaktir (M9.2) -
`expire_all()` kullanmak, duzelttigimizden DAHA CIDDI, sessiz bir veri
kaybi hatasi yaratirdi. Bunun yerine, YALNIZCA bu `account_id`'ye ait
`RunLockOrm` nesnesi (VARSA) `identity_key` ile bulunup hedefli
`Session.expire()` ile guncellenir - baska hicbir nesne etkilenmez.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy.orm.util import identity_key

from linkedinbot.db.models import RunLockOrm


class RunLock:
    """Hesap basina tek satirlik, DB tabanli cakisma-onleme kilidi (Roadmap M9.1)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _expire_cached_row(self, account_id: UUID) -> None:
        """Bu `account_id`'ye ait, ONCEDEN identity map'e yuklenmis olabilecek
        `RunLockOrm` nesnesini (varsa) hedefli olarak "expire" eder - boylece
        sonraki bir `session.get()`/erisim, Core-duzeyinde `acquire()`/
        `release()` ifadelerinin AZ ONCE yazdigi TAZE veriyi gorur. Yalnizca
        BU nesneyi etkiler; oturumdaki baska hicbir nesneye (orn. cagiranin
        ayni oturumda tasidigi flush-edilmemis baska degisikliklere)
        DOKUNMAZ (bkz. modul dokumani "Duzeltme notu").
        """
        key = identity_key(RunLockOrm, account_id)
        cached = self._session.identity_map.get(key)
        if cached is not None:
            self._session.expire(cached)

    def acquire(
        self,
        account_id: UUID,
        lock_owner: str,
        now: datetime,
        lock_duration: timedelta,
    ) -> bool:
        """Hesap icin kilidi almaya calisir.

        Satir hic yoksa VEYA mevcut kilit kilitsizse/suresi (`lock_expires_at
        < now`) dolmussa basarili olur; aksi halde (baska bir sahip icin
        hala gecerli bir kilit varsa) reddedilir. Tek bir atomik ifade
        icinde calisir - es zamanli cagirilarda guvenlidir.
        """
        expires_at = now + lock_duration
        stmt = pg_insert(RunLockOrm).values(
            account_id=account_id,
            locked_at=now,
            lock_owner=lock_owner,
            lock_expires_at=expires_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[RunLockOrm.account_id],
            set_={
                "locked_at": stmt.excluded.locked_at,
                "lock_owner": stmt.excluded.lock_owner,
                "lock_expires_at": stmt.excluded.lock_expires_at,
            },
            where=(RunLockOrm.locked_at.is_(None)) | (RunLockOrm.lock_expires_at < now),
        ).returning(RunLockOrm.account_id)

        result = self._session.execute(stmt)
        acquired = result.first() is not None
        self._expire_cached_row(account_id)
        return acquired

    def release(self, account_id: UUID, lock_owner: str) -> bool:
        """Kilidi serbest birakir - yalnizca `lock_owner` HALA eslesirse.

        Sahiplik eslesmiyorsa (veya kilit zaten bos/yoksa) sessiz bir
        no-op'tur - bu, bir baskasinin o arada aldigi YENI, gecerli bir
        kilidin yanlislikla silinmesini onler.
        """
        stmt = (
            update(RunLockOrm)
            .where(RunLockOrm.account_id == account_id, RunLockOrm.lock_owner == lock_owner)
            .values(locked_at=None, lock_owner=None, lock_expires_at=None)
            .returning(RunLockOrm.account_id)
        )
        result = self._session.execute(stmt)
        released = result.first() is not None
        self._expire_cached_row(account_id)
        return released
