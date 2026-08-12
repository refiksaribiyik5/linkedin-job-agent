"""AnthropicLLMAdapter icin birim testleri (Roadmap M5.1, retry M9.4).

Gercek Anthropic API'ye HICBIR ZAMAN dokunulmaz - `anthropic.Anthropic`
istemcisi tamamen sahtelenir (monkeypatch), M3.1-M3.5'in gercek
Playwright'a hic dokunmadan test etme desemiyle AYNI yaklasim. Gercek bir
API anahtariyla yapilan CANLI cagri, ayri bir entegrasyon testinde
(tests/integration/llm/test_anthropic_adapter_live.py) ele alinir ve
`ANTHROPIC_API_KEY` ortam degiskeni yoksa atlanir.

Proje talimatiyla acikca onaylanan kapsam: model kademelendirme, cache,
repair, zarif geri dusme (graceful degradation), prompt registry ve
skorlama mantigi KASITLI OLARAK burada YOKTUR - bunlar sirasiyla M5.3,
M5.3, M5.3, M5.2 ve M6/M7'nin kapsamidir. Retry (M9.4) ARTIK BURADADIR -
Section 21: "Yalnizca gecici hatalar (zaman asimi, 5xx, 429) yeniden
denenir." `retry_with_backoff()` (retry.py) araciligiyla, YALNIZCA
`anthropic.APITimeoutError`/`RateLimitError`/`InternalServerError`
`TransientError`e cevrilip yeniden denenir - BASKA herhangi bir istisna
(genel `RuntimeError`, `ValidationError` vb.) HALA hic yakalanmadan/
denenmeden dogrudan yukari sizar (M5.1'in "asla sessizce baska bir
sonuca donusturmez" ilkesi degismedi).
"""

from __future__ import annotations

from typing import Any

import anthropic
import httpx
import pytest
from pydantic import BaseModel, ValidationError

from linkedinbot.adapters.llm.anthropic_adapter import AnthropicLLMAdapter
from linkedinbot.errors import TransientError
from linkedinbot.ports.llm_provider_port import LLMProviderPort

TEST_MODEL = "claude-3-5-haiku-20241022"
_FAKE_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _recording_sleep():
    calls: list[float] = []

    def _sleep(seconds: float) -> None:
        calls.append(seconds)

    _sleep.calls = calls
    return _sleep


class _Sentiment(BaseModel):
    sentiment: str


class _FakeToolUseBlock:
    def __init__(self, input_dict: dict[str, Any], name: str = "extract_structured_response"):
        self.type = "tool_use"
        self.name = name
        self.input = input_dict
        self.id = "toolu_fake123"


class _FakeTextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _FakeMessage:
    def __init__(self, content: list):
        self.content = content


class _FakeMessagesResource:
    def __init__(self, response: _FakeMessage):
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs) -> _FakeMessage:
        self.calls.append(kwargs)
        return self._response


class _FakeAnthropicClient:
    def __init__(self, response: _FakeMessage):
        self.messages = _FakeMessagesResource(response)


def _make_adapter(**overrides) -> AnthropicLLMAdapter:
    kwargs = {
        "api_key": "fake-key",
        "llm_retry_attempts": 3,
        "retry_base_delay_ms": 0,
        "retry_max_delay_ms": 0,
    }
    kwargs.update(overrides)
    return AnthropicLLMAdapter(**kwargs)


def _adapter_with_response(
    response_content: list,
) -> tuple[AnthropicLLMAdapter, _FakeAnthropicClient]:
    fake_client = _FakeAnthropicClient(_FakeMessage(response_content))
    adapter = _make_adapter()
    adapter._client = fake_client  # gercek istemciyi sahteyle degistir
    return adapter, fake_client


def test_adapter_implements_llm_provider_port():
    adapter = _make_adapter()
    assert isinstance(adapter, LLMProviderPort)


def test_generate_structured_returns_validated_response_model_instance():
    adapter, _client = _adapter_with_response([_FakeToolUseBlock({"sentiment": "positive"})])

    result = adapter.generate_structured("Classify this.", _Sentiment, TEST_MODEL)

    assert isinstance(result, _Sentiment)
    assert result.sentiment == "positive"


def test_generate_structured_sends_the_given_model_and_prompt():
    adapter, client = _adapter_with_response([_FakeToolUseBlock({"sentiment": "positive"})])

    adapter.generate_structured("Classify this exact text.", _Sentiment, TEST_MODEL)

    assert len(client.messages.calls) == 1
    call = client.messages.calls[0]
    assert call["model"] == TEST_MODEL
    assert call["messages"] == [{"role": "user", "content": "Classify this exact text."}]


def test_generate_structured_forces_tool_use_matching_the_response_model_schema():
    adapter, client = _adapter_with_response([_FakeToolUseBlock({"sentiment": "positive"})])

    adapter.generate_structured("Classify this.", _Sentiment, TEST_MODEL)

    call = client.messages.calls[0]
    assert len(call["tools"]) == 1
    tool = call["tools"][0]
    assert tool["input_schema"] == _Sentiment.model_json_schema()
    assert call["tool_choice"] == {"type": "tool", "name": tool["name"]}


def test_generate_structured_ignores_leading_text_blocks_and_uses_the_tool_use_block():
    adapter, _client = _adapter_with_response(
        [_FakeTextBlock("thinking out loud..."), _FakeToolUseBlock({"sentiment": "negative"})]
    )

    result = adapter.generate_structured("Classify this.", _Sentiment, TEST_MODEL)

    assert result.sentiment == "negative"


def test_generate_structured_raises_when_no_tool_use_block_is_present():
    adapter, _client = _adapter_with_response([_FakeTextBlock("no tool call here")])

    with pytest.raises(RuntimeError, match="tool_use"):
        adapter.generate_structured("Classify this.", _Sentiment, TEST_MODEL)


def test_generate_structured_raises_validation_error_for_schema_mismatched_output():
    # Talimat: "Validate the response against the supplied Pydantic model
    # inside the adapter before returning it." Bozuk/semaya uymayan bir
    # cikti icin REPAIR/yeniden deneme YOKTUR - ham dogrulama hatasi
    # oldugu gibi yukari sizmalidir (repair M5.3'un kapsamidir).
    adapter, _client = _adapter_with_response([_FakeToolUseBlock({"wrong_field": "oops"})])

    with pytest.raises(ValidationError):
        adapter.generate_structured("Classify this.", _Sentiment, TEST_MODEL)


def test_generate_structured_does_not_catch_or_retry_on_generic_client_errors():
    # M9.4: yalnizca APITimeoutError/RateLimitError/InternalServerError
    # TransientError'e cevrilip yeniden denenir - genel bir RuntimeError
    # (or. beklenmedik bir istemci hatasi) HALA hic yakalanmadan/denenmeden
    # dogrudan yukari sizar. Cagri sayisi acikca sayilir - aksi halde "son
    # denemede hata firlatan bir retry dongusu" de bu testi (yanlislikla)
    # gecerdi.
    class _RaisingMessagesResource:
        def __init__(self):
            self.call_count = 0

        def create(self, **kwargs):
            self.call_count += 1
            raise RuntimeError("simulated API error")

    adapter = _make_adapter()
    messages_resource = _RaisingMessagesResource()
    adapter._client = type("_C", (), {"messages": messages_resource})()

    with pytest.raises(RuntimeError, match="simulated API error"):
        adapter.generate_structured("Classify this.", _Sentiment, TEST_MODEL)

    assert messages_resource.call_count == 1


def test_generate_structured_retries_on_api_timeout_and_recovers():
    class _FlakyMessagesResource:
        def __init__(self, failures_before_success: int, success_response: _FakeMessage):
            self._remaining_failures = failures_before_success
            self._success_response = success_response
            self.call_count = 0

        def create(self, **kwargs):
            self.call_count += 1
            if self._remaining_failures > 0:
                self._remaining_failures -= 1
                raise anthropic.APITimeoutError(request=_FAKE_REQUEST)
            return self._success_response

    sleep = _recording_sleep()
    adapter = _make_adapter(retry_base_delay_ms=10, retry_max_delay_ms=100, sleep=sleep)
    messages_resource = _FlakyMessagesResource(
        failures_before_success=2,
        success_response=_FakeMessage([_FakeToolUseBlock({"sentiment": "positive"})]),
    )
    adapter._client = type("_C", (), {"messages": messages_resource})()

    result = adapter.generate_structured("Classify this.", _Sentiment, TEST_MODEL)

    assert result.sentiment == "positive"
    assert messages_resource.call_count == 3
    assert len(sleep.calls) == 2


def test_generate_structured_retries_on_rate_limit_error():
    response = httpx.Response(429, request=_FAKE_REQUEST)

    class _RateLimitedThenOk:
        def __init__(self):
            self.call_count = 0

        def create(self, **kwargs):
            self.call_count += 1
            if self.call_count == 1:
                raise anthropic.RateLimitError("rate limited", response=response, body=None)
            return _FakeMessage([_FakeToolUseBlock({"sentiment": "positive"})])

    adapter = _make_adapter(retry_base_delay_ms=0, retry_max_delay_ms=0, sleep=_recording_sleep())
    messages_resource = _RateLimitedThenOk()
    adapter._client = type("_C", (), {"messages": messages_resource})()

    result = adapter.generate_structured("Classify this.", _Sentiment, TEST_MODEL)

    assert result.sentiment == "positive"
    assert messages_resource.call_count == 2


def test_generate_structured_retries_on_internal_server_error():
    response = httpx.Response(500, request=_FAKE_REQUEST)

    class _ServerErrorThenOk:
        def __init__(self):
            self.call_count = 0

        def create(self, **kwargs):
            self.call_count += 1
            if self.call_count == 1:
                raise anthropic.InternalServerError("server error", response=response, body=None)
            return _FakeMessage([_FakeToolUseBlock({"sentiment": "positive"})])

    adapter = _make_adapter(retry_base_delay_ms=0, retry_max_delay_ms=0, sleep=_recording_sleep())
    messages_resource = _ServerErrorThenOk()
    adapter._client = type("_C", (), {"messages": messages_resource})()

    result = adapter.generate_structured("Classify this.", _Sentiment, TEST_MODEL)

    assert result.sentiment == "positive"
    assert messages_resource.call_count == 2


def test_generate_structured_raises_transient_error_after_exhausting_all_retry_attempts():
    # M9.4: `_call_anthropic()` bilerek `TransientError`e cevirir (retry.py'nin
    # "yalnizca TransientError'i yakalar" sozlesmesiyle tutarli - collector.py'nin
    # LinkedIn tarafiyla AYNI desen); orijinal `anthropic.APITimeoutError`
    # `__cause__` olarak ZINCIRLENIR (kaybolmaz), ama firlatilan TUR
    # `TransientError`dir - ham SDK istisnasi degil.
    class _AlwaysTimesOut:
        def __init__(self):
            self.call_count = 0

        def create(self, **kwargs):
            self.call_count += 1
            raise anthropic.APITimeoutError(request=_FAKE_REQUEST)

    adapter = _make_adapter(
        llm_retry_attempts=2, retry_base_delay_ms=0, retry_max_delay_ms=0, sleep=_recording_sleep()
    )
    messages_resource = _AlwaysTimesOut()
    adapter._client = type("_C", (), {"messages": messages_resource})()

    with pytest.raises(TransientError) as exc_info:
        adapter.generate_structured("Classify this.", _Sentiment, TEST_MODEL)

    assert isinstance(exc_info.value.__cause__, anthropic.APITimeoutError)
    assert messages_resource.call_count == 2
