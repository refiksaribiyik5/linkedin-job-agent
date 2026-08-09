"""Blacklist Filter - FR-19 (Job & Company Exclusion) (Roadmap M6.1).

TDD Section 11.4: Blacklist filtreleme zincirinin EN BASINA yerlestirilir,
cunku "saf bir konfigurasyon-lookup islemidir (LLM veya karmasik hesaplama
gerektirmez)". Bu yuzden bu modul, `history/diff_engine.py` (M4.2) ile ayni
SAF fonksiyon desenini izler: hicbir repository/DB'ye erismez, LLM
Gateway'e ihtiyac duymaz.

`UserProfile.preferences` (M1.1, domain/user_profile.py) FR-19'un tek
somut icerigidir (`excluded_companies`, `excluded_job_ids`). Bu fonksiyon
dogrudan `Preferences`'i parametre olarak alir - `AccountContext`'in
tamamini degil: M6.1'in Roadmap'teki "Bagimliliklar: M2.2" notu, bu
verinin runtime'da (gelecekteki bir Orchestrator, M9) AccountContext
uzerinden nereden geldigini belirtir, bu fonksiyonun imzasini degil;
`diff_engine.py`'nin kendi minimal parametre yaklasimiyla tutarlidir.

Eslesme, TAM (case-sensitive) esitlik ile yapilir - PRD/TDD, Departman
filtresinin (FR-4) aksine Blacklist icin herhangi bir semantik/bulanik
eslesme talep etmez; TDD'nin "saf konfigurasyon-lookup" gerekcesiyle de
tutarlidir.

`confidence` alani her zaman `None` birakilir - blacklist ikili/
deterministik bir karardir, bir guven skoru tasimaz (bkz.
`domain/evaluated_job.py`'nin `FilterResult.confidence` alani, yalnizca
Department gibi probabilistik filtreler icin anlamlidir).
"""

from __future__ import annotations

from linkedinbot.domain.evaluated_job import FilterResult
from linkedinbot.domain.job_posting import JobPosting
from linkedinbot.domain.user_profile import Preferences


def filter_by_blacklist(job_posting: JobPosting, preferences: Preferences) -> FilterResult:
    if job_posting.company_id in preferences.excluded_companies:
        return FilterResult(
            passed=False,
            reason=f"Company '{job_posting.company_id}' is on the exclusion blacklist.",
        )
    if job_posting.job_id in preferences.excluded_job_ids:
        return FilterResult(
            passed=False,
            reason=f"Job '{job_posting.job_id}' is on the exclusion blacklist.",
        )
    return FilterResult(passed=True, reason="Not on the exclusion blacklist.")
