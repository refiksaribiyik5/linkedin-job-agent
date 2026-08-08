"""M1.4 seed script icin entegrasyon testi (Roadmap M1.4).

Roadmap M1.4 "Tamamlanma Dogrulamasi": "Seed sonrasi DB sorgulanir;
olusan hesap kimligiyle (henuz taslak) bir AccountContext kurulabildigi
dogrulanir." Bu test, gercek `config/system.defaults.yaml` +
`config/accounts/default.account.yaml` dosyalarina karsi tam seed akisini
calistirarak tam olarak bunu yapar - sentetik/ornek YAML fixture'lari
degil, bu milestone'un gercek teslim ettigi dosyalar kullanilir.

`db_session` fixture'i (bkz. conftest.py) test sonunda rollback yapar; bu
yuzden bu test gercek dev veritabanina hicbir kalici veri yazmaz (bkz.
cli.seed()'in `session` parametresi alip commit ETMEMESI, ozellikle bu
amacla tasarlandi).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from linkedinbot.cli import seed
from linkedinbot.config.loader import load_account_context
from linkedinbot.db.models import AccountConfigProfileOrm, AccountOrm, UserProfileOrm

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"


def test_seed_creates_account_user_profile_and_active_config_profile(db_session: Session):
    account = seed(CONFIG_DIR, db_session)

    assert account.account_id is not None

    orm_account = db_session.get(AccountOrm, account.account_id)
    assert orm_account is not None
    assert orm_account.display_name == "Refik Sarıbıyık"
    assert orm_account.status == "active"

    orm_profile = db_session.get(UserProfileOrm, account.account_id)
    assert orm_profile is not None
    assert "Strategy" in orm_profile.career_goals
    assert orm_profile.preferences_dealbreakers == {
        "excluded_companies": [],
        "excluded_job_ids": [],
    }

    orm_config_profile = db_session.get(AccountConfigProfileOrm, (account.account_id, 1))
    assert orm_config_profile is not None
    assert orm_config_profile.is_active is True
    assert orm_config_profile.config_version == 1


def test_seed_merges_account_overrides_onto_system_defaults(db_session: Session):
    account = seed(CONFIG_DIR, db_session)

    orm_config_profile = db_session.get(AccountConfigProfileOrm, (account.account_id, 1))

    # account_config_overrides'tan gelen degerler (default.account.yaml).
    assert orm_config_profile.target_criteria["locations"] == ["Istanbul"]
    assert orm_config_profile.target_criteria["workplace_types"] == ["On-site", "Hybrid"]
    assert orm_config_profile.report_format_settings["language"] == "en"

    # system.defaults.yaml'dan gelen, override edilmeyen kardes anahtarlar
    # ezilmeden korunmus olmalidir (deep-merge, wholesale-replace degil).
    assert set(orm_config_profile.target_criteria["departments"].keys()) == {
        "Sales & Business Development",
        "Strategy & Growth",
        "Marketing",
        "Trade, Logistics & Supply Chain",
        "Commercial",
        "Consulting",
    }
    assert orm_config_profile.target_criteria["experience_levels"] == [
        "Internship",
        "New Graduate",
        "Entry Level",
        "Graduate Program",
        "Management Trainee",
        "MT Program",
        "0-2 Years Experience",
        "Junior",
    ]
    assert orm_config_profile.report_format_settings["format"] == "Markdown"
    assert orm_config_profile.report_format_settings["top_matches_count"] == 10


def test_seed_ai_match_and_company_quality_weights_sum_to_one(db_session: Session):
    # FR-13'un "agirlik toplami %100" dogrulama kuralinin resmi bir
    # dogrulayicisi henuz yok (M2.1), ama seed edilen degerlerin PRD
    # Section 12.1/13.1 ile tutarli oldugunu simdiden kanitlar.
    account = seed(CONFIG_DIR, db_session)
    orm_config_profile = db_session.get(AccountConfigProfileOrm, (account.account_id, 1))

    assert sum(orm_config_profile.weights_ai_match.values()) == 1.0
    assert sum(orm_config_profile.weights_company_quality.values()) == 1.0


def test_account_context_can_be_built_from_seeded_data(db_session: Session):
    # Roadmap M1.4'un tam olarak istedigi dogrulama: seed edilen hesap
    # kimligiyle bir AccountContext kurulabilmelidir. M2.2'den once bu test
    # AccountContext'i yalnizca account_id+user_profile ile elle
    # kuruyordu (o zamanki tek gecerli sekil buydu); M2.2, AccountContext'e
    # zorunlu config_version/config_profile alanlarini eklediginden ve
    # bunlari dogru sekilde doldurmanin GERCEK yolu artik
    # `load_account_context()`'tir - bu test o gercek yolu kullanacak
    # sekilde guncellendi (M1.4'un kendi verisi/davranisi degismedi).
    account = seed(CONFIG_DIR, db_session)

    account_context = load_account_context(account.account_id, db_session)

    assert account_context.account_id == account.account_id
    assert account_context.config_version == 1
    assert account_context.user_profile.career_goals.startswith("Build a career")
