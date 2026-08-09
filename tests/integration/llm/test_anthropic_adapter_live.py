"""AnthropicLLMAdapter icin CANLI entegrasyon testi (Roadmap M5.1).

Roadmap M5.1 "Tamamlanma Dogrulamasi": "Entegrasyon testi bir gercek
cagri yapar, yanitin beklenen semaya uydugunu dogrular." Bu test GERCEKTEN
Anthropic API'sine bir agi istegi yapar - `tests/unit/adapters/llm/test_anthropic_adapter.py`'nin
aksine (tamamen sahte istemciyle calisir).

`ANTHROPIC_API_KEY` ortam degiskeni ayarlanmamissa bu test ATLANIR -
bu ortamda gercek bir Anthropic API anahtari yoktur (M3.1-M3.5'in gercek
bir LinkedIn hesabina erisimi olmamasiyla AYNI, acikca belgelenmis
sinirlama). Gercek bir anahtarla calistirilip calistirilmadigini
projenin sahibi dogrulamalidir.
"""

from __future__ import annotations

import os

import pytest
from pydantic import BaseModel

from linkedinbot.adapters.llm.anthropic_adapter import AnthropicLLMAdapter

_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
_TEST_MODEL = "claude-3-5-haiku-20241022"

pytestmark = pytest.mark.skipif(
    not _API_KEY,
    reason="ANTHROPIC_API_KEY ayarlanmamis - gercek Anthropic API cagrisi atlanir.",
)


class _Sentiment(BaseModel):
    sentiment: str


def test_generate_structured_makes_a_real_call_and_returns_a_conforming_response():
    adapter = AnthropicLLMAdapter(api_key=_API_KEY)

    result = adapter.generate_structured(
        "Classify the sentiment of this sentence as exactly one of: "
        "positive, negative, neutral. Sentence: 'I love sunny days.'",
        _Sentiment,
        _TEST_MODEL,
    )

    assert isinstance(result, _Sentiment)
    assert result.sentiment.strip() != ""
