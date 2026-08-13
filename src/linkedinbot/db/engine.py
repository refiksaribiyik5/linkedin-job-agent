"""SQLAlchemy engine ve oturum (session) fabrikasi.

TDD Section 13 ("Konfigurasyon Mimarisi") geregi, DATABASE_URL yalnizca bir
altyapi ayaridir ve dogrudan ortam degiskenlerinden okunur -- konfigurasyon
onceligi zinciri (varsayilanlar -> sistem defaults -> hesap profili -> env)
Config Loader'in (M2.2) isidir, bu modulun degil.

`pool_pre_ping` (Roadmap M10.1 duzeltmesi, implementasyon sirasinda bulunan
bir bulgu, kullanicidan acikca onaylandi): varsayilan olarak KAPALIDIR -
`create_db_engine()`'in TUM MEVCUT cagiranlari (kisa-omurlu CLI komutlari,
testler) icin davranis DEGISMEZ. `main.py` (M10.1), gunler boyunca acik
kalan TEK bir `Session` tutan `APSchedulerAdapter`'in `account_repository`'si
icin bunu ACIKCA `True` yaparak enjekte eder - SQLAlchemy'nin KENDI onerdigi,
standart bir azaltma onlemidir (havuzdaki bir baglantiyi kullanmadan once
hafif bir "canli mi" kontrolu), araya giren bir DB baglanti kopmasinin
(yeniden baslatma, ag kesintisi) zamanlanmis calistirmayi surec yeniden
baslatilana kadar sessizce durdurmasini onlemek icin (bkz. `main.py`
modul dokumani).
"""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = "postgresql+psycopg://linkedinbot:changeme@localhost:5432/linkedinbot"


def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def create_db_engine(database_url: str | None = None, pool_pre_ping: bool = False) -> Engine:
    return create_engine(database_url or get_database_url(), pool_pre_ping=pool_pre_ping)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
