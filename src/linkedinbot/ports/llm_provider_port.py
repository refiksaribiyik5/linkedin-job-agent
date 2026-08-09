"""LLMProviderPort - yapilandirilmis (semaya uygun) LLM cikti uretimi
icin soyut arayuz (Roadmap M5.1, TDD Section 2/6).

TDD Section 2: "LLM Saglayici: Anthropic Claude API (varsayilan),
`LLMProvider` arayuzu arkasinda." Section 6 modul sorumluluklari
tablosu, `filtering`/`scoring.company_scoring`/`scoring.ai_matching`
modullerinin hepsinin `llm_provider_port`'a bagimli oldugunu belirtir -
ama bu modullerin HICBIRI henuz insa edilmedi (Faz 6/7). Bu Port, o
GELECEKTEKI cagiranlarin ihtiyac duyacagi TEK, GENEL ("herhangi bir
Pydantic semasina uygun yapilandirilmis cikti uret") yetenegi tanimlar -
proje talimatiyla acikca onaylandi.

M5.1 KAPSAMI: Port yalnizca `generate_structured()` - TEK bir GENEL
metod - icerir. Asagidakiler KASITLI OLARAK burada YOKTUR (Roadmap'in
kendi ayirdigi sonraki milestone'larin kapsamidir):
- Model kademelendirme (TDD Section 10 tablosu) - Roadmap M5.3.
- Onbellekleme (Section 12.4/FR-18) - Roadmap M5.3/Faz 7.
- Yeniden deneme (retry) - Roadmap M9.3.
- "Repair" yeniden istemi - Roadmap M5.3.
- Zarif geri dusme ("Scoring Unavailable") - Roadmap M5.3.
- Prompt sablon yonetimi - Roadmap M5.2.
- Herhangi bir skorlama/filtreleme is mantigi - Faz 6/7.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


class LLMProviderPort(ABC):
    """Bir LLM saglayicisindan, verilen bir Pydantic semasina uygun
    yapilandirilmis cikti almanin soyut arayuzu."""

    @abstractmethod
    def generate_structured(
        self, prompt: str, response_model: type[ResponseModelT], model: str
    ) -> ResponseModelT:
        """`prompt`'u `model`'e gonderir, yaniti `response_model`'in
        semasina gore dogrulayip o modelin bir ornegi olarak doner.

        Yanit semaya uymuyorsa (veya cagri basarisiz olursa), ozgun hata
        (orn. bir Pydantic `ValidationError`) OLDUGU GIBI yukari sizar -
        bu metod hicbir sekilde yeniden denemez, "onarmaya" calismaz veya
        basarisizligi sessizce baska bir sonuca donusturmez (bkz. modul
        dokumaninin M5.1 KAPSAMI notu).
        """
