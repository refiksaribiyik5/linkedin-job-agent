"""SQLAlchemy engine ve oturum (session) fabrikasi.

TDD Section 13 ("Konfigurasyon Mimarisi") geregi, DATABASE_URL yalnizca bir
altyapi ayaridir ve dogrudan ortam degiskenlerinden okunur -- konfigurasyon
onceligi zinciri (varsayilanlar -> sistem defaults -> hesap profili -> env)
Config Loader'in (M2.2) isidir, bu modulun degil.
"""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = "postgresql+psycopg://linkedinbot:changeme@localhost:5432/linkedinbot"


def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def create_db_engine(database_url: str | None = None) -> Engine:
    return create_engine(database_url or get_database_url())


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
