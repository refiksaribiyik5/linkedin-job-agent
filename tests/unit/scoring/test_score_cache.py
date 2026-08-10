"""scoring/score_cache.py icin birim testleri (Roadmap M7.1, TDD v1.1 Fix
3 / Section 12.4).

Section 12.4: "Onbellek anahtari Company ID + Weight Profile ID + Rubric
Version uclusudur." `weight_profile_id` NULL = sistem varsayilani (TDD
Section 15, `company_scores` semasi) - bu yuzden `None` GECERLI, AYRI bir
anahtar bilesenidir (bkz. `db/models.py`'nin iki kismi-unique index'i:
`weight_profile_id IS NULL` vs `IS NOT NULL`).

Bu modul SAF'tir (`diff_engine.py`/M4.2 ile ayni desen): hicbir depoya
erismez, cagirandan bir "onbellek" dict'i alir ve o dict uzerinde
sadece OKUMA yapar - yazma/kalicilik sorumlulugu cagirana aittir
(gercek DB kalicilik, `CompanyScoreOrm` uzerinden, henuz insa edilmemis
bir orkestratorun - M9 - isidir).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from linkedinbot.scoring.company_scoring import CompanyScore
from linkedinbot.scoring.score_cache import get_cached_score

EVALUATED_AT = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def _company_score(**overrides) -> CompanyScore:
    data = {
        "company_id": "Acme Corp",
        "weight_profile_id": None,
        "rubric_version": 1,
        "score_total": 80.0,
        "score_breakdown": {},
        "evaluated_at": EVALUATED_AT,
    }
    data.update(overrides)
    return CompanyScore(**data)


def test_returns_none_for_an_empty_cache():
    result = get_cached_score({}, "Acme Corp", None, 1)

    assert result is None


def test_returns_the_cached_score_on_an_exact_key_match():
    cached = _company_score()
    cache = {("Acme Corp", None, 1): cached}

    result = get_cached_score(cache, "Acme Corp", None, 1)

    assert result == cached


def test_misses_when_rubric_version_differs():
    cache = {("Acme Corp", None, 1): _company_score(rubric_version=1)}

    result = get_cached_score(cache, "Acme Corp", None, 2)

    assert result is None


def test_misses_when_weight_profile_id_differs():
    # NULL (sistem varsayilani) ile bir hesaba-ozel weight_profile_id AYRI
    # anahtarlardir - biri digerinin onbellegini yanlislikla kullanmamali.
    custom_profile_id = uuid4()
    cache = {("Acme Corp", None, 1): _company_score(weight_profile_id=None)}

    result = get_cached_score(cache, "Acme Corp", custom_profile_id, 1)

    assert result is None


def test_misses_when_company_id_differs():
    cache = {("Acme Corp", None, 1): _company_score()}

    result = get_cached_score(cache, "Other Corp", None, 1)

    assert result is None
