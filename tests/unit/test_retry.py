"""retry.py icin birim testleri (Roadmap M9.4, TDD Section 21).

TDD Section 21: "Üstel geri çekilme (exponential backoff) + jitter,
sınırlı deneme sayısı." `retry_with_backoff()` bu mekanizmanin PAYLASILAN
implementasyonudur - `TransientError` (errors.py) firlatildiginda yeniden
dener, HERHANGI baska bir istisnayi (or. `PermanentError`) HIC yakalamadan
dogrudan yukari birakir (Section 20'nin "yalnizca sinifladigi hatayi
yakalar" ilkesi).

Sahte `sleep` enjeksiyonu, bu projenin `collection/collector.py`'nin
(M3.5) zaten kurdugu AYNI desenidir - gercek bekleme suresi olmadan
zamanlamayi/cagri sayisini dogrulamak icin.
"""

from __future__ import annotations

import pytest
from linkedinbot.retry import retry_with_backoff

from linkedinbot.errors import PermanentError, TransientError


class _RecordingSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _scripted_fn(outcomes: list):
    """outcomes: bir listedeki HER eleman ya bir Exception ORNEGI (raise
    edilir) ya da duz bir deger (return edilir). Cagrilar sirayla listeyi
    tuketir."""
    calls = {"count": 0}

    def fn():
        outcome = outcomes[calls["count"]]
        calls["count"] += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    fn.call_count = lambda: calls["count"]  # noqa: E731
    return fn


def test_succeeds_on_first_try_without_sleeping():
    sleep = _RecordingSleep()
    fn = _scripted_fn(["ok"])

    result = retry_with_backoff(
        fn, max_attempts=3, base_delay_ms=100, max_delay_ms=1000, sleep=sleep
    )

    assert result == "ok"
    assert fn.call_count() == 1
    assert sleep.calls == []


def test_retries_after_transient_error_and_eventually_succeeds():
    sleep = _RecordingSleep()
    fn = _scripted_fn([TransientError("timeout"), TransientError("timeout"), "ok"])

    result = retry_with_backoff(
        fn, max_attempts=3, base_delay_ms=100, max_delay_ms=1000, sleep=sleep
    )

    assert result == "ok"
    assert fn.call_count() == 3
    assert len(sleep.calls) == 2  # iki basarisiz deneme arasinda iki bekleme


def test_exhausting_all_attempts_raises_the_last_transient_error():
    sleep = _RecordingSleep()
    fn = _scripted_fn(
        [TransientError("first"), TransientError("second"), TransientError("third")]
    )

    with pytest.raises(TransientError, match="third"):
        retry_with_backoff(fn, max_attempts=3, base_delay_ms=100, max_delay_ms=1000, sleep=sleep)

    assert fn.call_count() == 3
    assert len(sleep.calls) == 2  # ucuncu (son) basarisizliktan SONRA bekleme YOK


def test_non_transient_error_propagates_immediately_without_retrying():
    # Section 20: yalnizca TransientError retry mekanizmasina girer -
    # PermanentError (veya baska HERHANGI bir istisna) hic yakalanmaz.
    sleep = _RecordingSleep()
    fn = _scripted_fn([PermanentError("invalid session"), "ok"])

    with pytest.raises(PermanentError, match="invalid session"):
        retry_with_backoff(fn, max_attempts=3, base_delay_ms=100, max_delay_ms=1000, sleep=sleep)

    assert fn.call_count() == 1
    assert sleep.calls == []


def test_max_attempts_of_one_disables_retry_entirely():
    sleep = _RecordingSleep()
    fn = _scripted_fn([TransientError("timeout"), "ok"])

    with pytest.raises(TransientError):
        retry_with_backoff(fn, max_attempts=1, base_delay_ms=100, max_delay_ms=1000, sleep=sleep)

    assert fn.call_count() == 1
    assert sleep.calls == []


def test_backoff_delay_grows_exponentially_and_is_capped_at_max_delay_ms():
    sleep = _RecordingSleep()
    fn = _scripted_fn(
        [
            TransientError("1"),
            TransientError("2"),
            TransientError("3"),
            TransientError("4"),
            "ok",
        ]
    )

    retry_with_backoff(fn, max_attempts=5, base_delay_ms=100, max_delay_ms=350, sleep=sleep)

    # 4 bekleme: ustel buyume 100, 200, 400(->350 cap), 350(cap) ms - +-25%
    # jitter ile, ama HER ZAMAN saniyeye cevrilir (ms / 1000) ve asla negatif
    # olamaz.
    assert len(sleep.calls) == 4
    expected_ms_before_jitter = [100, 200, 350, 350]  # 400 -> 350 cap
    for actual_seconds, expected_ms in zip(sleep.calls, expected_ms_before_jitter, strict=True):
        assert actual_seconds >= 0
        lower_bound_seconds = (expected_ms * 0.75) / 1000
        upper_bound_seconds = (expected_ms * 1.25) / 1000
        assert lower_bound_seconds <= actual_seconds <= upper_bound_seconds
