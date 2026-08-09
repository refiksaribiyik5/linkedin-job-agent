"""LLMGateway - PromptRegistry + LLMProviderPort'u tek bir "repair'li"
cagriya birlestirir (Roadmap M5.3, TDD Section 10/21).

TDD Section 10 (Grounding zorunlulugu): "Cikti... dogrulanir; semaya
uymayan ... bir madde uretilirse tek bir 'repair' yeniden istemi denenir,
yine basarisiz olursa ... 'tahmin uretmek yerine' 'Scoring Unavailable'
olarak isaretlenir." TDD Section 21: "Yalnizca gecici hatalar (zaman
asimi, 5xx, 429) yeniden denenir[;] [y]apisal olarak bozuk ... cikti icin
tek bir 'repair' yeniden istemi denenir." Bu ikisi birbirinden AYRI iki
mekanizmadir: gecici/agi hatalari icin retry Roadmap M9.3'un
kapsamidir (ortak bir retry/backoff modulu, M5.1'in cagri noktasini
GUNCELLEYECEK) - burada YOKTUR. Bu modul yalnizca YAPISAL/sema
dogrulama hatasini (Pydantic `ValidationError`) ele alir; baska HERHANGI
bir istisna (orn. `AnthropicLLMAdapter`'in ham istemci hatalari veya
"tool_use bulunamadi" RuntimeError'i) hicbir sekilde yakalanmaz, oldugu
gibi yukari sizar.

"Scoring Unavailable" temsili: Bu kod tabaninin zaten kurdugu kongvansiyona
uyularak `None` kullanilir - bkz. `EvaluatedJob.ai_match_score: float |
None` ve `company_scores.score_total (NUMERIC, NULL = Unrated)` (TDD
satir 451). Ayri bir sentinel string turu icat edilmez.

Model kademelendirmesi (TDD Section 10 tablosu - 4 cagri turunu 3 model
kademesine esler): Bu tablonun asil caGiran taraflari (department
matching / experience inference / company scoring / AI match rationale
servisleri) henuz insa edilmedi (Faz 6/7). Bu milestone'da somut bir
"cagri turu -> model adi" esleme tablosu KASITLI OLARAK eklenmez - bu,
henuz var olmayan caGiranlar icin spekulatif bir altyapi olurdu. Bunun
yerine M5.1'in zaten kurdugu desen korunur: `model`, `generate()`'e
caGiran tarafindan verilen duz bir parametredir - Gateway hicbir modeli
kendi icinde sabitlemez, boylece gercek kademelendirme karari, o karari
verecek bilgiye sahip olan GELECEKTEKI caGirana birakilir.

KASITLI OLARAK YAPILMAYANLAR (Roadmap'in ayirdigi sonraki
milestone'larin kapsamidir): gecici hata retry/backoff (M9.3), skor
onbellekleme (Section 12.4/FR-18, Faz 6/7), cagri turu->model esleme
tablosu (Faz 6/7), skorlama/filtreleme/siralama mantigi (Faz 6/7).
"""

from __future__ import annotations

from pydantic import ValidationError

from linkedinbot.adapters.llm.prompt_registry import PromptRegistry
from linkedinbot.ports.llm_provider_port import LLMProviderPort, ResponseModelT


def _build_repair_prompt(original_prompt: str, error: ValidationError) -> str:
    return (
        f"{original_prompt}\n\n"
        "Your previous response did not match the required schema. "
        f"Validation error: {error}\n"
        "Please try again, making sure your output conforms exactly to the schema."
    )


class LLMGateway:
    def __init__(self, llm_provider: LLMProviderPort, prompt_registry: PromptRegistry) -> None:
        self._llm_provider = llm_provider
        self._prompt_registry = prompt_registry

    def generate(
        self,
        template_name: str,
        response_model: type[ResponseModelT],
        model: str,
        **template_variables: str,
    ) -> ResponseModelT | None:
        prompt = self._prompt_registry.render(template_name, **template_variables)
        try:
            return self._llm_provider.generate_structured(prompt, response_model, model)
        except ValidationError as first_error:
            repair_prompt = _build_repair_prompt(prompt, first_error)
            try:
                return self._llm_provider.generate_structured(repair_prompt, response_model, model)
            except ValidationError:
                return None
