"""LinkedInBot CLI (TDD Section 5) - manuel komutlar.

M1.4: yalnizca `seed` komutu eklenir - V1'in tek hesabini, kullanici
profilini ve ilk (config_version=1, is_active=true) config profilini
`config/system.defaults.yaml` + `config/accounts/default.account.yaml`
dosyalarindan olusturur (Roadmap M1.4). `config validate` (M2.4) ve `run`
(M9.6) komutlari sonraki milestone'larda bu dosyaya eklenecektir - bu
yuzden `cli.py`, ayri bir `scripts/seed.py` yerine burada baslatilir
(TDD Section 5'in dosya agacinda zaten `cli.py` ayrilmistir, `scripts/`
diye bir dizin hic yoktur).

Bu modul, M2.1/M2.2'nin tam config sema/dogrulama/oncelik-zinciri
mantigini ONCEDEN UYGULAMAZ - yalnizca iki YAML dosyasini okuyup birlestirip
DB'ye bir kere yazan minimal bir bootstrap islemidir (bkz. `_deep_merge`
ve `seed` fonksiyonlarinin dokumanlari).
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from linkedinbot.db.engine import create_db_engine, create_session_factory
from linkedinbot.db.models import AccountConfigProfileOrm
from linkedinbot.db.repositories.account_repository import SqlAlchemyAccountRepository
from linkedinbot.db.repositories.user_profile_repository import SqlAlchemyUserProfileRepository
from linkedinbot.domain.account import Account
from linkedinbot.domain.user_profile import Preferences, UserProfile


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Ic-ice (nested) dict'ler icin basit birlestirme: `overrides`'taki her
    anahtar `base`'i ezer; iki tarafta da dict olan degerler recursive
    olarak birlestirilir (orn. `target_criteria.locations` ezilirken
    `target_criteria.departments` sistem varsayilanindan korunur).

    Bu, TDD Section 23'un tam oncelik zinciri (kod-ici varsayilanlar ->
    system.defaults.yaml -> DB'deki hesap profili -> ortam degiskenleri)
    DEGILDIR - yalnizca seed script'inin system.defaults.yaml + hesaba-ozel
    `account_config_overrides`'i BIR KEZ, seed anında birlestirmesi icin
    kullanilan minimal bir yardimcidir. Tam yukleme zinciri M2.2'nin isidir.
    """
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def seed(config_dir: Path, session: Session) -> Account:
    """Roadmap M1.4 "Beklenen Sonuç": bos bir veritabanina karsi calistirildiginda
    bir `accounts` satiri, bir `user_profiles` satiri ve
    `config_version=1, is_active=true` olan bir `account_config_profiles`
    satiri olusturur.

    Bu fonksiyon `session`'i CAGIRMAZ/COMMIT ETMEZ - transaction sinirini
    cagiran yonetir (bkz. `_run_seed_command`). Bu, M1.3'un repository
    test desenini (rollback edilen bir `db_session` fixture'i) burada da
    kullanabilmeyi saglar; aksi halde her test calistirmasi gercek
    dev veritabanina kalici, tekrar-eden hesaplar commit ederdi.

    Bu fonksiyon, populated bir veritabanina karsi TEKRAR calistirilmaya
    karsi guvenli DEGILDIR (idempotent degildir) - Roadmap M1.4'un
    Tamamlanma Dogrulamasi yalnizca bos bir veritabanini kapsar; bu
    kasitli bir sinirlamadir, V1'in tek seferlik bootstrap akisinin
    (bkz. M10.2) otesinde henuz bir gereksinim degildir.
    """
    system_defaults = yaml.safe_load((config_dir / "system.defaults.yaml").read_text())
    account_seed = yaml.safe_load((config_dir / "accounts" / "default.account.yaml").read_text())

    overrides = account_seed.get("account_config_overrides", {})
    config_profile_data = _deep_merge(system_defaults, overrides)

    now = datetime.now(UTC)
    account_repo = SqlAlchemyAccountRepository(session)
    user_profile_repo = SqlAlchemyUserProfileRepository(session)

    account = account_repo.create(
        Account(
            display_name=account_seed["display_name"],
            created_at=now,
            status=account_seed.get("status", "active"),
        )
    )

    user_profile_repo.create(
        account.account_id,
        UserProfile(
            career_goals=account_seed["career_goals"].strip(),
            skills_summary=account_seed["skills_summary"].strip(),
            preferences=Preferences(**account_seed.get("preferences", {})),
        ),
    )

    # account_config_profiles icin M1.3'te kasitli olarak henuz bir
    # repository/Port yoktur (AccountConfigProfile domain modeli
    # M2.1'de tanimlanacak) - bu tek satir dogrudan ORM ile yazilir
    # (bkz. M1.4 onay kaydi). TDD Section 15'in composite PK'sini
    # (account_id, config_version) dogrudan kullanir.
    config_profile = AccountConfigProfileOrm(
        account_id=account.account_id,
        config_version=1,
        target_criteria=config_profile_data["target_criteria"],
        weights_ai_match=config_profile_data["weights_ai_match"],
        weights_company_quality=config_profile_data["weights_company_quality"],
        thresholds=config_profile_data["thresholds"],
        schedule=config_profile_data["schedule"],
        collection_limits=config_profile_data["collection_limits"],
        notification_settings=config_profile_data["notification_settings"],
        report_format_settings=config_profile_data["report_format_settings"],
        prompt_template_refs=config_profile_data["prompt_template_refs"],
        is_active=True,
        # NOT: `validated_at`, bu satirin YAZILDIGI zamani tasir - FR-13'un
        # gercek sema/agirlik-toplami dogrulamasi (M2.1) burada henuz
        # CALISMAZ. Bu alanin "gercekten dogrulandi" degil "bu haliyle
        # kaydedildi" anlamina geldigi acikca not edilir; M2.1 kendi
        # dogrulamasini calistirdiginda bu alani gunceller.
        validated_at=now,
    )
    session.add(config_profile)
    session.flush()

    return account


def _run_seed_command(config_dir: Path) -> None:
    """`seed()`'in gercek CLI cagrisi icin sarmalayicisi: engine/session'i
    kurar, transaction sinirini (commit/rollback) yonetir.
    """
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    session: Session = session_factory()
    try:
        account = seed(config_dir, session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()

    print(f"Seed tamamlandi: account_id={account.account_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="linkedinbot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser(
        "seed", help="V1'in tek hesabini ve ilk config profilini olusturur (Roadmap M1.4)."
    )
    seed_parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("config"),
        help="system.defaults.yaml ve accounts/ alt dizinini iceren dizin (varsayilan: ./config).",
    )

    args = parser.parse_args(argv)

    if args.command == "seed":
        _run_seed_command(args.config_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
