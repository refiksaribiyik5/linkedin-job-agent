"""AnthropicLLMAdapter - `LLMProviderPort`'un Anthropic Claude implementasyonu
(Roadmap M5.1, retry M9.4).

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
onbellekleme, "repair," zarif geri dusme, prompt sablonlama. Semaya
uymayan bir yanit (`ValidationError`) burada HALA YAKALANMAZ - oldugu
gibi yukari sizar (repair Roadmap M5.3'un kapsamidir).

**Retry (M9.4, TDD Section 21 "Yalnizca gecici hatalar (zaman asimi,
5xx, 429) yeniden denenir"):** `_call_anthropic()`, `self._client.messages.create()`
cagrisini sarmalayip YALNIZCA `anthropic.APITimeoutError`/`RateLimitError`/
`InternalServerError`'i (Section 21'in "zaman asimi"/429/5xx orneklerinin
BIREBIR karsiligi) `errors.TransientError`e cevirir; `retry_with_backoff()`
(retry.py) bu ucunu yakalayip yeniden dener. BASKA HERHANGI bir istisna
(kimlik dogrulama hatasi, `ValidationError`, tool_use eksikligi
`RuntimeError`'i) HIC yakalanmadan/denenmeden dogrudan yukari sizar -
M5.1'in "asla sessizce baska bir sonuca donusturmez" ilkesi bunlar icin
DEGISMEDI, yalnizca UC BELIRLI, gercekten gecici SDK istisnasi icin bir
istisna eklendi.

`llm_retry_attempts`/`retry_base_delay_ms`/`retry_max_delay_ms` KASITLI
OLARAK varsayilansizdir (`collection/collector.py`'nin retry parametreleriyle
AYNI ilke - NFR-6/Config-Is Mantigi Ayrimi geregi kod icine gomulu bir
varsayilan YOKTUR); `sleep`'in varsayilani GERCEK `time.sleep`'tir
(collector.py'nin `_apply_rate_limit`'iyle AYNI "hiz sinirlamasi acikca
devre disi birakilmadikca HER ZAMAN calisir" guvenli varsayilani).
"""

from __future__ import annotations

import time
from collections.abc import Callable

import anthropic

from linkedinbot.errors import TransientError
from linkedinbot.ports.llm_provider_port import LLMProviderPort, ResponseModelT
from linkedinbot.retry import retry_with_backoff

# Yapilandirilmis cikti, tek bir "tool" cagrisinin argumanlari olarak
# donecegi icin (serbest metin degil), bu deger sabit ve kucuktur - bir
# is-kurali/konfigurasyon degeri degil, saf bir teknik sinirdir.
_MAX_TOKENS = 1024
_TOOL_NAME = "extract_structured_response"

# TDD Section 21: "zaman asimi, 5xx, 429" - Anthropic SDK'sinin bu UC
# somut kategoriye karsilik gelen istisna siniflari.
_TRANSIENT_ANTHROPIC_ERRORS = (
    anthropic.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


class AnthropicLLMAdapter(LLMProviderPort):
    def __init__(
        self,
        api_key: str,
        llm_retry_attempts: int,
        retry_base_delay_ms: int,
        retry_max_delay_ms: int,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._llm_retry_attempts = llm_retry_attempts
        self._retry_base_delay_ms = retry_base_delay_ms
        self._retry_max_delay_ms = retry_max_delay_ms
        self._sleep = sleep

    def _call_anthropic(self, prompt: str, response_model: type[ResponseModelT], model: str):
        try:
            return self._client.messages.create(
                model=model,
                max_tokens=_MAX_TOKENS,
                tools=[
                    {
                        "name": _TOOL_NAME,
                        "description": (
                            f"Extract structured data matching {response_model.__name__}."
                        ),
                        "input_schema": response_model.model_json_schema(),
                    }
                ],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
                messages=[{"role": "user", "content": prompt}],
            )
        except _TRANSIENT_ANTHROPIC_ERRORS as exc:
            raise TransientError(str(exc)) from exc

    def generate_structured(
        self, prompt: str, response_model: type[ResponseModelT], model: str
    ) -> ResponseModelT:
        def _attempt() -> ResponseModelT:
            response = self._call_anthropic(prompt, response_model, model)
            for block in response.content:
                if block.type == "tool_use":
                    return response_model.model_validate(block.input)
            raise RuntimeError(
                f"Anthropic yaniti bir tool_use blogu icermiyor (model: {model!r}) - "
                "beklenen yapilandirilmis cikti alinamadi."
            )

        return retry_with_backoff(
            _attempt,
            max_attempts=self._llm_retry_attempts,
            base_delay_ms=self._retry_base_delay_ms,
            max_delay_ms=self._retry_max_delay_ms,
            sleep=self._sleep,
        )
