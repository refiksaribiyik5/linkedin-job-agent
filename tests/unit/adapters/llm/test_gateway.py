"""LLMGateway icin birim testleri (Roadmap M5.3).

Roadmap M5.3 "Tamamlanma Dogrulamasi": "Sahte (mock) bir provider ile:
(a) once bozuk sonra gecerli JSON donduren senaryoda repair yolunun
kullanildigi, (b) iki kez de bozuk donduren senaryoda hatasiz 'Scoring
Unavailable' sonucunun dondugu dogrulanir."

Gercek Anthropic API'ye HICBIR ZAMAN dokunulmaz - `LLMProviderPort`
tamamen sahtelenir (M5.1'in kendi test deseniyle AYNI yaklasim: hand-rolled
fake, gercek SDK/agi yok). `PromptRegistry` ise M5.2'nin GERCEK sinifidir
(sahte degil) - Gateway'in PromptRegistry'yi dogru cagirdigini, izole bir
`tmp_path` sablonuyla dogrular.

"Scoring Unavailable" (TDD Section 10/21), bu kod tabaninin zaten
kullandigi kongvansiyona uygun olarak `None` ile temsil edilir - bkz.
`EvaluatedJob.ai_match_score: float | None` ve
`company_scores.score_total (NUMERIC, NULL = Unrated)` (TDD satir 451);
ayri bir sentinel string turu icat edilmez.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from linkedinbot.adapters.llm.gateway import LLMGateway
from linkedinbot.adapters.llm.prompt_registry import PromptRegistry
from linkedinbot.ports.llm_provider_port import LLMProviderPort

TEST_MODEL = "claude-3-5-haiku-20241022"


class _Sentiment(BaseModel):
    sentiment: str


def _validation_error() -> ValidationError:
    try:
        _Sentiment.model_validate({"wrong_field": "oops"})
    except ValidationError as error:
        return error
    raise AssertionError("expected a ValidationError")


class _ScriptedProvider(LLMProviderPort):
    """Sirali bir sonuc/istisna listesini her cagrida bir sonraki elemanla
    yanitlayan sahte saglayici (M5.1'in kendi hand-rolled fake desenindeki
    ayni yaklasim, ama sirali senaryolar icin genellestirilmis)."""

    def __init__(self, script: list):
        self._script = list(script)
        self.calls: list[dict] = []

    def generate_structured(self, prompt, response_model, model):
        self.calls.append({"prompt": prompt, "response_model": response_model, "model": model})
        outcome = self._script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def prompt_registry(tmp_path: Path) -> PromptRegistry:
    (tmp_path / "greeting.prompt.md").write_text(
        "Hello, ${name}! Classify the sentiment.", encoding="utf-8"
    )
    return PromptRegistry(tmp_path)


def test_generate_renders_the_named_template_and_returns_first_attempt_result(prompt_registry):
    provider = _ScriptedProvider([_Sentiment(sentiment="positive")])
    gateway = LLMGateway(llm_provider=provider, prompt_registry=prompt_registry)

    result = gateway.generate("greeting", _Sentiment, TEST_MODEL, name="Ada")

    assert result == _Sentiment(sentiment="positive")
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call["prompt"] == "Hello, Ada! Classify the sentiment."
    assert call["response_model"] is _Sentiment
    assert call["model"] == TEST_MODEL


def test_generate_retries_once_with_a_repair_prompt_when_output_is_invalid_then_succeeds(
    prompt_registry,
):
    error = _validation_error()
    provider = _ScriptedProvider([error, _Sentiment(sentiment="negative")])
    gateway = LLMGateway(llm_provider=provider, prompt_registry=prompt_registry)

    result = gateway.generate("greeting", _Sentiment, TEST_MODEL, name="Ada")

    assert result == _Sentiment(sentiment="negative")
    assert len(provider.calls) == 2
    first_prompt = provider.calls[0]["prompt"]
    second_prompt = provider.calls[1]["prompt"]
    assert first_prompt == "Hello, Ada! Classify the sentiment."
    assert second_prompt != first_prompt
    assert first_prompt in second_prompt
    assert provider.calls[1]["response_model"] is _Sentiment
    assert provider.calls[1]["model"] == TEST_MODEL


def test_generate_returns_none_when_the_repair_attempt_also_fails(prompt_registry):
    provider = _ScriptedProvider([_validation_error(), _validation_error()])
    gateway = LLMGateway(llm_provider=provider, prompt_registry=prompt_registry)

    result = gateway.generate("greeting", _Sentiment, TEST_MODEL, name="Ada")

    assert result is None
    assert len(provider.calls) == 2


def test_generate_does_not_repair_or_retry_on_non_validation_errors(prompt_registry):
    provider = _ScriptedProvider([RuntimeError("simulated client error")])
    gateway = LLMGateway(llm_provider=provider, prompt_registry=prompt_registry)

    with pytest.raises(RuntimeError, match="simulated client error"):
        gateway.generate("greeting", _Sentiment, TEST_MODEL, name="Ada")

    assert len(provider.calls) == 1


def test_generate_does_not_swallow_non_validation_errors_from_the_repair_attempt(
    prompt_registry,
):
    # ValidationError'in kendisi disinda hicbir istisna "repair" tarafindan
    # yakalanmaz - bu, ilk deneme icin zaten test edilmisti; bu test ayni
    # garantiyi REPAIR denemesinin kendisi icin de dogrular (repair sonrasi
    # ham bir istemci hatasi da oldugu gibi yukari sizmali, sessizce
    # None'a donusturulmemeli).
    provider = _ScriptedProvider([_validation_error(), RuntimeError("simulated repair error")])
    gateway = LLMGateway(llm_provider=provider, prompt_registry=prompt_registry)

    with pytest.raises(RuntimeError, match="simulated repair error"):
        gateway.generate("greeting", _Sentiment, TEST_MODEL, name="Ada")

    assert len(provider.calls) == 2
