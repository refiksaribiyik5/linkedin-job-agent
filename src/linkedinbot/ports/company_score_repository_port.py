"""CompanyScoreRepositoryPort - company_scores tablosu icin soyut arayuz
(Roadmap M9.2, FR-18, PRD Section 12.4).

`company_scores`, M1.2'de zaten olusturulmus (`CompanyScoreOrm`,
degistirilmemis) ama M7.1'in kendi modul dokumaninin acikca not ettigi
gibi hicbir repository/port'la sarilmamis bir tablodur - Roadmap M9.2 bu
bosluğu kapatir. `CompanyScore` (M7.1, degistirilmemis) `domain/` altinda
degil `scoring/company_scoring.py` altinda tanimlidir; bu, M7.1'in kendi
onaylanmis yerlesim karari - bu Port o kararı degistirmez, sadece mevcut
tipi import eder.

`CompanyScore` importu KASITLI OLARAK `TYPE_CHECKING` altindadir ve
`pyproject.toml`'daki "Ports katmani somut db/adapters implementasyonlarini
import edemez" kontrati bu TEK kenar icin acikca bir `ignore_imports`
istisnasi tasir: `scoring/company_scoring.py`, `CompanyScore`'un KENDISIYLE
ilgisi olmayan bir nedenle (yalnizca `score_company()`'nin imzasi icin)
`LLMGateway`'i (`linkedinbot.adapters`) de import eder, bu da `CompanyScore`'u
import etmeyi gecisken (transitive) olarak `adapters`'a baglar. Bu, `ports`
katmaninin somut adaptorlere bagimli olmamasi gerektigi kuralinin GERCEK
bir ihlali degildir (bu Port hicbir zaman `LLMGateway`'e dokunmaz) - bu
istisna, o kuralı BASKA HICBIR YER icin gevsetmeden bu MEKANIK, ilgisiz
kenari acikca ve dar kapsamda yok sayar (bkz. `pyproject.toml`'daki
kontrat yorumu).

**Kapsam (Roadmap M9.2'nin kendi Amac metninden BIREBIR):** Yalnizca
kalicilik saglanir. `score_company()`, `score_cache.py` ve Company
Quality puanlama kurallari (Section 12.1'in alti boyutu/agirliklari)
bu Port tarafindan hicbir sekilde degistirilmez veya cagrilmaz - bu
Port'un tek is'i, cagiranin ZATEN sahip oldugu bir `CompanyScore`
nesnesini yazmak/okumaktir.

**Tazelik penceresi (freshness window) BURADA degerlendirilmez:**
`get_by_key()`, bulunan kaydi (varsa) HAM olarak doner -
`evaluated_at`'in `Thresholds.company_score_reevaluation_window_days`
icinde olup olmadigina karar vermek, Roadmap M9.2'nin kendi Amac
metninin acikca belirttigi gibi Orchestrator'in (M9.3) sorumlulugunda
kalir. Bu Port bir "onbellek" degil, salt bir depodur.

**`create()`/`update()` neden AYRI (upsert() DEGIL) - Roadmap
degisikligi sirasinda acikca tartisilan ve onaylanan karar:** Projedeki
HER DIGER repository (Account/Job/Company/EvaluatedJob/Report/RunLog)
ayni deseni kullanir - cagiran, ONCEDEN yaptigi bir `get_by_key()`
(veya esdegeri) sorgusundan HANGI metodun cagrilacagini ZATEN bilir, bu
yuzden ayri create/update ekstra bir sorgu maliyeti getirmez. `RunLock`
(M9.1) tek istisnadir ve bilincli bir sapmadir - o, gercek bir
CAPRAZ-SUREC yaris durumunu (concurrent acquire) cozen atomik bir
`INSERT ... ON CONFLICT` gerektirir. `CompanyScore` icin boyle bir
yaris yoktur: V1 tek hesaplidir ve `RunLock` zaten o hesap icin
eszamanli calistirmalari engeller; bu yuzden upsert semantigi burada
cozulecek gercek bir sorunu olmayan, tutarliligi bozan bir sapma
olurdu.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from linkedinbot.scoring.company_scoring import CompanyScore


class CompanyScoreRepositoryPort(ABC):
    """company_scores tablosu icin temel create/read/update islemleri (Roadmap M9.2)."""

    @abstractmethod
    def create(self, company_score: CompanyScore) -> CompanyScore:
        """Yeni bir sirket skoru satiri olusturur."""

    @abstractmethod
    def get_by_key(
        self, company_id: str, weight_profile_id: UUID | None, rubric_version: int
    ) -> CompanyScore | None:
        """PRD Section 12.4'un uc parcali onbellek anahtariyla arar.
        Skor bulunamazsa None doner.
        """

    @abstractmethod
    def update(self, company_score: CompanyScore) -> CompanyScore:
        """Var olan bir sirket skoru satirini gunceller (anahtar:
        `company_id` + `weight_profile_id` + `rubric_version`).
        """
