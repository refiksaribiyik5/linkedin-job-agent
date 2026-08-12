"""ports/linkedin_port.py icin birim testleri (Roadmap M9.4).

`SessionInvalidError`'in `errors.py`'nin (M9.4, "Hata Siniflandirma +
Retry") `PermanentError`'indan turemesi, M3.2'nin kendi modul
dokumaninda ONCEDEN acikca beklenen bir gelecek adimdi: "Gecersiz bir
oturum SessionInvalidError firlatir; TDD Section 20'nin hata
taksonomisinde bu bir PermanentError olarak siniflandirilir (retry
edilmez) - ama o merkezi taksonomi sinifi ... henuz insa edilmemistir
... bu yuzden SessionInvalidError simdilik bagimsiz ... tanimlanir."
"""

from __future__ import annotations

from linkedinbot.errors import PermanentError
from linkedinbot.ports.linkedin_port import SessionInvalidError


def test_session_invalid_error_is_a_permanent_error():
    assert issubclass(SessionInvalidError, PermanentError)


def test_session_invalid_error_carries_a_message():
    error = SessionInvalidError("LinkedIn session expired")
    assert str(error) == "LinkedIn session expired"
