"""errors.py icin birim testleri (Roadmap M9.4, TDD Section 20).

TDD Section 20'nin hata taksonomisi tablosu: `TransientError` (Retry
mekanizmasina girer) ve `PermanentError` (Retry edilmez; Run "Failed"
olarak sonlanir). Bu modul bu iki sinifi, `retry.py`'nin (henuz insa
edilmemis, ayni milestone) TEK tuketicisi olmadigini yansitacak sekilde
SIFIR bagimlilikla tanimlar - bkz. modul dokumani.
"""

from __future__ import annotations

from linkedinbot.errors import PermanentError, TransientError


def test_transient_error_is_an_exception():
    assert issubclass(TransientError, Exception)


def test_permanent_error_is_an_exception():
    assert issubclass(PermanentError, Exception)


def test_transient_and_permanent_error_are_not_related_to_each_other():
    # Ikisi de bagimsiz, KARDES siniflardir - biri digerinin alt sinifi
    # DEGILDIR (bir except TransientError bloğu yanlislikla bir
    # PermanentError'i da yakalamamalidir, ve tam tersi).
    assert not issubclass(TransientError, PermanentError)
    assert not issubclass(PermanentError, TransientError)


def test_transient_error_carries_a_message():
    error = TransientError("LinkedIn request timed out")
    assert str(error) == "LinkedIn request timed out"


def test_permanent_error_carries_a_message():
    error = PermanentError("Invalid session")
    assert str(error) == "Invalid session"
