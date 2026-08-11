"""SqlAlchemyCompanyScoreRepository icin entegrasyon testleri (Roadmap
M9.2, FR-18, PRD Section 12.4).

Roadmap M9.2 "Tamamlanma Dogrulamasi": "Birim testleri (gercek test
DB'sine karsi): bir CompanyScore olusturulur ve ayni anahtarla
get_by_key ile geri okunur; farkli bir rubric_version veya
weight_profile_id ile ayni company_id'nin AYRI bir kayit olusturdugu
(Section 12.4 cok-kullanicili onbellekleme kurali) dogrulanir; update()
var olan kaydi degistirir; get_by_key bulunamayan bir anahtar icin None
doner."

Bu modul, YALNIZCA kaliciligi test eder - `score_company()`,
`score_cache.py` veya tazelik penceresi (freshness window) mantigi
BURADA test EDILMEZ (Roadmap M9.2'nin kendi kapsam siniri: bu Port ham
`get_by_key` sonucunu doner, `evaluated_at`'in tazelik penceresi
icinde olup olmadigina karar vermek M9.3'un (Orchestrator) isidir).

`CompanyScoreOrm.company_id`, `companies` tablosuna bir FOREIGN KEY
tasir (M1.2) - bu yuzden her test, mevcut `company` fixture'ini
(tests/integration/db/conftest.py) kullanir.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from linkedinbot.db.models import CompanyOrm
from linkedinbot.db.repositories.company_score_repository import (
    SqlAlchemyCompanyScoreRepository,
)
from linkedinbot.ports.company_score_repository_port import CompanyScoreRepositoryPort
from linkedinbot.scoring.company_scoring import CompanyScore

NOW = datetime(2026, 8, 11, tzinfo=UTC)


def _company_score(company_id: str, **overrides) -> CompanyScore:
    data = {
        "company_id": company_id,
        "weight_profile_id": None,
        "rubric_version": 1,
        "score_total": 72.5,
        "score_breakdown": {
            "brand_reputation_prestige": 80.0,
            "company_scale": 70.0,
            "career_development_training_culture": 65.0,
            "sector_position": 75.0,
            "corporate_stability": 70.0,
            "external_signals": 75.0,
        },
        "evaluated_at": NOW,
    }
    data.update(overrides)
    return CompanyScore(**data)


def test_repository_implements_port(db_session: Session):
    repo = SqlAlchemyCompanyScoreRepository(db_session)
    assert isinstance(repo, CompanyScoreRepositoryPort)


def test_create_and_get_by_key_round_trip(db_session: Session, company: CompanyOrm):
    repo = SqlAlchemyCompanyScoreRepository(db_session)
    score = _company_score(company.company_id)

    created = repo.create(score)
    fetched = repo.get_by_key(company.company_id, None, 1)

    assert fetched is not None
    assert fetched.company_id == created.company_id
    assert fetched.weight_profile_id is None
    assert fetched.rubric_version == 1
    assert fetched.score_total == 72.5
    assert fetched.score_breakdown == score.score_breakdown
    assert fetched.evaluated_at == NOW


def test_get_by_key_returns_none_when_not_found(db_session: Session, company: CompanyOrm):
    repo = SqlAlchemyCompanyScoreRepository(db_session)

    assert repo.get_by_key(company.company_id, None, 1) is None


def test_different_rubric_version_creates_a_separate_record(
    db_session: Session, company: CompanyOrm
):
    # PRD Section 12.4: Rubric Version, sistem varsayilan puanlama
    # mantigi degistiginde eski skorlarin yanlislikla yeniden
    # kullanilmasini onlemek icin onbellek anahtarinin bir parcasidir.
    repo = SqlAlchemyCompanyScoreRepository(db_session)
    repo.create(_company_score(company.company_id, rubric_version=1, score_total=50.0))
    repo.create(_company_score(company.company_id, rubric_version=2, score_total=90.0))

    v1 = repo.get_by_key(company.company_id, None, 1)
    v2 = repo.get_by_key(company.company_id, None, 2)

    assert v1 is not None
    assert v2 is not None
    assert v1.score_total == 50.0
    assert v2.score_total == 90.0


def test_different_weight_profile_id_creates_a_separate_record(
    db_session: Session, company: CompanyOrm
):
    # PRD Section 12.4 cok-kullanicili onbellekleme kurali: sistem
    # varsayilan agirlikla (weight_profile_id=None) hesaplanan skor,
    # hesaba ozel bir agirlik profiliyle hesaplanan skordan AYRI
    # tutulur - ikisi de AYNI company_id + rubric_version'a sahip
    # olsa bile.
    custom_weight_profile_id = uuid4()
    repo = SqlAlchemyCompanyScoreRepository(db_session)
    repo.create(
        _company_score(company.company_id, weight_profile_id=None, score_total=50.0)
    )
    repo.create(
        _company_score(
            company.company_id, weight_profile_id=custom_weight_profile_id, score_total=95.0
        )
    )

    system_default = repo.get_by_key(company.company_id, None, 1)
    custom = repo.get_by_key(company.company_id, custom_weight_profile_id, 1)

    assert system_default is not None
    assert custom is not None
    assert system_default.score_total == 50.0
    assert custom.score_total == 95.0
    assert system_default.weight_profile_id != custom.weight_profile_id


def test_update_changes_the_existing_record(db_session: Session, company: CompanyOrm):
    repo = SqlAlchemyCompanyScoreRepository(db_session)
    repo.create(_company_score(company.company_id, score_total=50.0))

    later = datetime(2026, 9, 10, tzinfo=UTC)
    updated = repo.update(
        _company_score(
            company.company_id,
            score_total=88.0,
            score_breakdown={"brand_reputation_prestige": 90.0},
            evaluated_at=later,
        )
    )

    assert updated.score_total == 88.0
    assert updated.score_breakdown == {"brand_reputation_prestige": 90.0}
    assert updated.evaluated_at == later

    fetched = repo.get_by_key(company.company_id, None, 1)
    assert fetched is not None
    assert fetched.score_total == 88.0


def test_update_raises_when_no_matching_record_exists(db_session: Session, company: CompanyOrm):
    repo = SqlAlchemyCompanyScoreRepository(db_session)

    with pytest.raises(ValueError):
        repo.update(_company_score(company.company_id))


def test_unrated_score_persists_with_none_total_and_empty_breakdown(
    db_session: Session, company: CompanyOrm
):
    # M7.1's score_company(): LLM Gateway basarisiz olursa score_total=None,
    # score_breakdown={} (bos dict, None DEGIL) ile "Unrated" doner - bu
    # kayit sekli PRD 12.3 geregi kalici olarak dogru temsil edilmelidir.
    repo = SqlAlchemyCompanyScoreRepository(db_session)
    repo.create(_company_score(company.company_id, score_total=None, score_breakdown={}))

    fetched = repo.get_by_key(company.company_id, None, 1)

    assert fetched is not None
    assert fetched.score_total is None
    assert fetched.score_breakdown == {}


def test_score_total_precision_matches_the_database_after_create(
    db_session: Session, company: CompanyOrm
):
    # M1.3 review duzeltmesinin (evaluated_job_repository.py'deki
    # ai_match_score ile AYNI Numeric(5,2) sutunu) BURADA da gecerli
    # olan sonucu: Postgres 2 ondalik basamaktan fazla bir deger
    # verildiginde SESSIZCE yuvarlar. Donen nesne, flush() sonrasi
    # session.refresh() cagrilmadan cagiranin gonderdigi
    # YUVARLANMAMIS degeri tasirdi - bu, DB'nin fiilen sakladigindan
    # sessizce sapan bir donus degeri olurdu.
    repo = SqlAlchemyCompanyScoreRepository(db_session)

    created = repo.create(_company_score(company.company_id, score_total=72.566))

    assert created.score_total == 72.57
    fetched = repo.get_by_key(company.company_id, None, 1)
    assert fetched is not None
    assert fetched.score_total == 72.57


def test_score_total_precision_matches_the_database_after_update(
    db_session: Session, company: CompanyOrm
):
    repo = SqlAlchemyCompanyScoreRepository(db_session)
    repo.create(_company_score(company.company_id, score_total=50.0))

    updated = repo.update(_company_score(company.company_id, score_total=33.334))

    assert updated.score_total == 33.33


def test_score_breakdown_whole_number_values_round_trip_as_floats(
    db_session: Session, company: CompanyOrm
):
    # Self-review bulgusu (dogrulanmis, GERCEK bir hata DEGIL - ama
    # aciklayici bir regresyon testi hak eden ince bir davranis): JSON
    # int/float ayrimini korumaz, bu yuzden `score_breakdown`'daki tam
    # sayili bir float (orn. 100.0), JSONB'den psycopg araciligiyla ham
    # bir Python `int` olarak donebilirdi. `CompanyScore.score_breakdown:
    # dict[str, float | None]`'in Pydantic dogrulamasi bunu SESSIZCE
    # `float`'a geri yukseltir (lax mod, varsayilan) - REPL'de ampirik
    # olarak dogrulandi. Bu test, bu davranisi gelecekte (orn. Pydantic
    # strict mod'a gecilirse) sessizce bozulmaya karsi kalici olarak
    # sabitler.
    repo = SqlAlchemyCompanyScoreRepository(db_session)
    repo.create(
        _company_score(
            company.company_id,
            score_breakdown={"brand_reputation_prestige": 100.0, "company_scale": 0.0},
        )
    )

    fetched = repo.get_by_key(company.company_id, None, 1)

    assert fetched is not None
    assert fetched.score_breakdown == {"brand_reputation_prestige": 100.0, "company_scale": 0.0}
    assert all(isinstance(v, float) for v in fetched.score_breakdown.values())
