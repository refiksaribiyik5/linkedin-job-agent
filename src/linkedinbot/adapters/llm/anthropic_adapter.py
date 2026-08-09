"""AnthropicLLMAdapter - `LLMProviderPort`'un Anthropic Claude implementasyonu
(Roadmap M5.1).

Yapilandirilmis (semaya uygun) cikti, Anthropic'in KENDI "tool use"
mekanizmasi ile saglanir (proje talimatiyla acikca onaylandi): verilen
`response_model`'in JSON semasi tek bir "tool" olarak tanimlanir ve
`tool_choice` ile modelin bu tool'u KULLANMASI ZORUNLU kilinir - bu,
modelin serbest metin yerine semaya uygun bir JSON nesnesi uretmesini
GARANTI ETMEYE calisan, Anthropic'in kendi onerdigi standart yontemdir.
Donen `tool_use` blogunun `input`'u (zaten ayristirilmis bir dict),
`response_model.model_validate()` ile DOGRULANIR - bu, talimatin acikca
istedigi "adapter icinde, donmeden once dogrulama" adimidir.

KASITLI OLARAK YAPILMAYANLAR (proje talimatiyla acikca onaylandi, bkz.
ports/llm_provider_port.py'nin modul dokumani): model kademelendirme,
onbellekleme, yeniden deneme, "repair," zarif geri dusme, prompt
sablonlama. Semaya uymayan bir yanit (`ValidationError`) veya API
cagrisi hatasi (herhangi bir `anthropic` istisnasi) burada YAKALANMAZ -
oldugu gibi yukari sizar (bu davranislarin hepsi Roadmap M5.3/M9.3'un
kapsamidir).
"""

from __future__ import annotations

import anthropic

from linkedinbot.ports.llm_provider_port import LLMProviderPort, ResponseModelT

# Yapilandirilmis cikti, tek bir "tool" cagrisinin argumanlari olarak
# donecegi icin (serbest metin degil), bu deger sabit ve kucuktur - bir
# is-kurali/konfigurasyon degeri degil, saf bir teknik sinirdir.
_MAX_TOKENS = 1024
_TOOL_NAME = "extract_structured_response"


class AnthropicLLMAdapter(LLMProviderPort):
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate_structured(
        self, prompt: str, response_model: type[ResponseModelT], model: str
    ) -> ResponseModelT:
        response = self._client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            tools=[
                {
                    "name": _TOOL_NAME,
                    "description": f"Extract structured data matching {response_model.__name__}.",
                    "input_schema": response_model.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
            messages=[{"role": "user", "content": prompt}],
        )

        for block in response.content:
            if block.type == "tool_use":
                return response_model.model_validate(block.input)

        raise RuntimeError(
            f"Anthropic yaniti bir tool_use blogu icermiyor (model: {model!r}) - "
            "beklenen yapilandirilmis cikti alinamadi."
        )
