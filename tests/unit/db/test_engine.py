"""db/engine.py icin birim testleri (Roadmap M10.1).

`pool_pre_ping` (Roadmap M10.1 duzeltmesi, implementasyon sirasinda
bulunan bir bulgu): `main.py`'nin uzun-omurlu zamanlayici sureci, hesap
basina TEK bir `Session`'i (`APSchedulerAdapter`'in `account_repository`'si
icin, M9.6'nin degistirilmemis constructor sekli) gunler boyunca acik
tutar - araya giren bir DB baglanti kopmasi (yeniden baslatma, ag kesintisi)
BIR SONRAKI ateslemenin `_account_repository.get_by_id()`/`.update()`
cagrisini basarisiz kilar ve bu istisna `_fire()`'in yeniden-kurma
kuyrugunu (`add_job()`) HIC calistirmadan biter - hesabin zamanlamasi
surec yeniden baslatilana kadar SESSIZCE oluverir. `pool_pre_ping=True`,
SQLAlchemy'nin havuzdaki bir baglantiyi kullanmadan ONCE hafif bir
"canli mi" kontrolu yapmasini saglayan, kutuphanenin KENDI onerdigi,
standart bir azaltma onlemidir - bu, `create_db_engine()`'in TUM MEVCUT
cagiranlari (kisa-omurlu CLI komutlari, testler) icin varsayilan davranisi
DEGISTIRMEYEN, geriye-donuk-uyumlu, opsiyonel bir parametre olarak eklenir.
"""

from __future__ import annotations

from linkedinbot.db.engine import create_db_engine


def test_create_db_engine_defaults_to_pool_pre_ping_disabled():
    # Mevcut TUM cagiranlar (kisa-omurlu CLI komutlari/testler) icin
    # davranis DEGISMEMELIDIR.
    engine = create_db_engine()
    try:
        assert engine.pool._pre_ping is False
    finally:
        engine.dispose()


def test_create_db_engine_can_enable_pool_pre_ping():
    engine = create_db_engine(pool_pre_ping=True)
    try:
        assert engine.pool._pre_ping is True
    finally:
        engine.dispose()
