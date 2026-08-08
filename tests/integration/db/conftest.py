"""tests/integration/db/ altindaki tum entegrasyon testleri icin paylasilan
fixture'lar (M1.2'de test_schema.py'de tanimlanmis, M1.3'te birden fazla
test dosyasi (repository testleri) ayni fixture'lara ihtiyac duydugu icin
buraya tasindi - pytest, ayni dizindeki conftest.py'yi otomatik kesfeder).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from linkedinbot.db.engine import create_db_engine, create_session_factory
from linkedinbot.db.models import AccountConfigProfileOrm, AccountOrm, CompanyOrm

NOW = datetime.now(UTC)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Tum test oturumu boyunca paylasilan tek bir Engine (ve connection
    pool). Her testte yeniden Engine olusturup atmak gereksiz maliyetlidir;
    izolasyon Engine seviyesinde degil, her testin kendi rollback edilen
    transaction'inda saglanir (bkz. db_session).
    """
    eng = create_db_engine()
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """Her test sonunda geri alinan (rollback) bir transaction icinde
    calisan oturum. Engine testler arasinda paylasilir (yukarida).
    """
    factory = create_session_factory(engine)
    session: Session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def account(db_session: Session) -> AccountOrm:
    acc = AccountOrm(display_name="Test Hesabi", created_at=NOW, status="active")
    db_session.add(acc)
    db_session.flush()
    return acc


@pytest.fixture
def company(db_session: Session) -> CompanyOrm:
    comp = CompanyOrm(
        company_id="test-company", name="Test A.S.", first_seen_at=NOW, last_updated_at=NOW
    )
    db_session.add(comp)
    db_session.flush()
    return comp


@pytest.fixture
def make_config_profile():
    """AccountConfigProfileOrm icin, tum JSONB alanlarini bos sozlukle
    dolduran bir fabrika. Birden fazla testte tekrarlanan 8 satirlik
    boilerplate'i tek bir yerde toplar.
    """

    def _make(account_id: uuid.UUID, config_version: int = 1, is_active: bool = True):
        return AccountConfigProfileOrm(
            account_id=account_id,
            config_version=config_version,
            target_criteria={},
            weights_ai_match={},
            weights_company_quality={},
            thresholds={},
            schedule={},
            collection_limits={},
            notification_settings={},
            report_format_settings={},
            prompt_template_refs={},
            is_active=is_active,
            validated_at=NOW,
        )

    return _make
