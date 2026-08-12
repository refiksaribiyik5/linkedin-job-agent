"""Paylasilan geri-cekilme (retry/backoff) mekanizmasi (TDD Section 21,
Roadmap M9.4).

Bu modul YALNIZCA `errors.py`'nin TASIDIGI `TransientError` sinifini
TUKETIR - taksonomiyi kendisi TANIMLAMAZ (bkz. errors.py modul
dokumani: "sahiplik ters-donuklugu"). `collection/collector.py`
(LinkedIn cagri noktasi) ve `adapters/llm/anthropic_adapter.py` (LLM
cagri noktasi) bu fonksiyonun IKI bagimsiz tuketicisidir - HER biri
KENDI transient/permanent siniflandirmasini yapip `TransientError`'e
CEVIRIR, sonra bu fonksiyonu cagirir (TDD Section 20: "Her modul
yalnizca kendi siniflandirabilecegi hatayi yakalar ve normalize edilmis
bir istisna turu olarak yukari firlatir").

**Neden `TransientError` DISINDA HERHANGI bir istisna hic yakalanmaz:**
Section 20'nin taksonomisi `PermanentError`'i acikca "Retry edilmez"
olarak tanimlar - bu fonksiyon bu ayrimi ZORUNLU KILAR: yalnizca
`TransientError` yeniden deneme dongusune girer, baska HERHANGI bir
istisna (PermanentError dahil) DERHAL, HICBIR bekleme olmadan yukari
sizar.

**Geri cekilme formulu:** `min(base_delay_ms * 2**(deneme-1),
max_delay_ms)` - Section 21'in "ustel geri cekilme" ifadesinin birebir
karsiligi; `retry_max_delay_ms` bu buyumeyi sinirlar (config alaninin
KENDI var olma gerekcesi). Jitter, `collection/collector.py`'nin
(M3.5) `_apply_rate_limit()` ile AYNI simetrik-uniform desenle
uygulanir - ancak M3.5'in aksine (ayri bir `jitter_seconds` config
alani alir) burada SABIT bir oran (hesaplanan gecikmenin +-%25'i)
kullanilir: Roadmap'in onayladigi bes yeni alan arasinda ayri bir
jitter-orani parametresi YOKTUR, bu yuzden jitter, KENDI BASINA
konfigure edilebilir bir deger degil, ZATEN konfigure edilebilir olan
gecikmenin sabit bir TUREVIDIR.

**Neden hicbir zaman `errors.py`'nin KENDISI degil, yalnizca cagiranlar
`TransientError` firlatir:** Bu fonksiyon KENDI BASINA hicbir agi/LLM
cagrisi yapmaz - saf bir kontrol-akisi sarmalayicisidir; `fn: Callable[[],
T]` parametresi cagiranin ZATEN transient/permanent ayrimini yapmis
oldugu bir kapatma (closure)'dir.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable

from linkedinbot.errors import TransientError

_JITTER_PROPORTION = 0.25


def _backoff_delay_ms(attempt: int, base_delay_ms: int, max_delay_ms: int) -> float:
    exponential_delay_ms = min(base_delay_ms * (2 ** (attempt - 1)), max_delay_ms)
    jitter_ms = exponential_delay_ms * _JITTER_PROPORTION
    # S311 (flake8-bandit "kriptografik olmayan RNG") burada bir yanlis-
    # pozitiftir: bu jitter, collection/collector.py'nin _apply_rate_limit()'i
    # ile AYNI gerekceyle guvenlik/kriptografi disidir.
    jittered_delay_ms = exponential_delay_ms + random.uniform(-jitter_ms, jitter_ms)  # noqa: S311
    return max(0.0, jittered_delay_ms)


def retry_with_backoff[T](
    fn: Callable[[], T],
    *,
    max_attempts: int,
    base_delay_ms: int,
    max_delay_ms: int,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """`fn()`'i cagirir; `TransientError` firlatirsa ve deneme hakki
    kaldiysa ustel geri cekilme + jitter ile bekleyip yeniden dener.
    Deneme hakki kalmadiginda SON `TransientError` oldugu gibi yukari
    firlatilir. `TransientError` DISINDAKI herhangi bir istisna hic
    yakalanmadan DERHAL yukari sizar (bkz. modul dokumani).

    `sleep` saniye alir (stdlib `time.sleep` sozlesmesi) - `base_delay_ms`/
    `max_delay_ms` milisaniye cinsinden verildigi icin cagirmadan once
    1000'e bolunur.
    """
    attempt = 1
    while True:
        try:
            return fn()
        except TransientError:
            if attempt >= max_attempts:
                raise
            delay_ms = _backoff_delay_ms(attempt, base_delay_ms, max_delay_ms)
            sleep(delay_ms / 1000)
            attempt += 1
