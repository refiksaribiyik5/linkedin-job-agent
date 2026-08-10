"""Company Score Cache - duzeltilmis 3 parcali onbellek anahtari (Roadmap
M7.1, TDD v1.1 Fix 3, Section 12.4).

Section 12.4: "Onbellek anahtari Company ID + Weight Profile ID + Rubric
Version uclusudur." `weight_profile_id` NULL degeri "sistem varsayilani"
anlamina gelir (TDD Section 15 `company_scores` semasi) - `None` GECERLI,
diger herhangi bir degerden AYRI bir anahtar bilesenidir; bu yuzden basit
bir `dict.get()` yeterlidir (Python'da `None` normal, hash'lenebilir bir
deger olarak zaten dogru calisir - ozel bir "NULL kolonu" isleme mantigi
gerekmez).

Bu modul SAF'tir: hicbir depoya/DB'ye erismez. Cagiran, "onbellek"i (bir
onceki `score_company()` cagrilarindan biriktirilmis bir dict) acikca
parametre olarak verir - `history/diff_engine.py`'nin (M4.2) "gecmis
kayitlari cagiran verir" deseniyle AYNI. Gercek kalicilik (bir DB satirini
okuma/yazma), `CompanyScoreOrm` (M1.2, degistirilmemis) uzerinden,
henuz insa edilmemis bir orkestratorun (M9) isidir.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from linkedinbot.scoring.company_scoring import CompanyScore

CacheKey = tuple[str, UUID | None, int]


def get_cached_score(
    cache: dict[CacheKey, CompanyScore],
    company_id: str,
    weight_profile_id: UUID | None,
    rubric_version: int,
) -> CompanyScore | None:
    return cache.get((company_id, weight_profile_id, rubric_version))
