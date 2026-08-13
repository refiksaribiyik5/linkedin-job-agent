"""bootstrap.py icin birim testleri (Roadmap M10.1).

`build_dependencies()`'in tam kablolamasi (SessionManager/AnthropicLLMAdapter/
vb.) gercek disaridan sistemlere (OS keychain, Playwright, Anthropic)
dokunmadan otomatik olarak test edilemez - bu, `cli.py`'nin M9.7'deki
`_run_run_command` testlerinin ZATEN yaptigi gibi, `build_dependencies()`'i
BUTUNUYLE monkeypatch ile degistirerek dolayli olarak dogrulanir (bkz.
tests/unit/test_cli.py). Burada YALNIZCA gercekten izole test edilebilen
saf mantik (`_require_secret`) dogrudan test edilir.
"""

from __future__ import annotations

import pytest

from linkedinbot import bootstrap


class _FakeSecretsProvider:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self._values = dict(values or {})

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def set(self, key: str, value: str) -> None:
        self._values[key] = value


def test_require_secret_returns_the_value_when_present():
    provider = _FakeSecretsProvider({"anthropic_api_key": "sk-ant-test"})

    assert bootstrap._require_secret(provider, "anthropic_api_key") == "sk-ant-test"


def test_require_secret_raises_value_error_naming_the_key_when_missing():
    provider = _FakeSecretsProvider({})

    with pytest.raises(ValueError, match="anthropic_api_key"):
        bootstrap._require_secret(provider, "anthropic_api_key")
