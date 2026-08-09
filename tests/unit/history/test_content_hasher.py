"""history/content_hasher.py icin birim testleri (Roadmap M4.2).

`compute_content_hash` (M4.1, normalization/normalizer.py) ZATEN hesaplama
mantigini icerir - bu modul onu TEKRAR ETMEZ, yalnizca iki ZATEN
hesaplanmis hash'i KARSILASTIRIR (Diff Engine'in "degisti mi?" sorusunun
tek satirlik cevabi).
"""

from __future__ import annotations

from linkedinbot.history.content_hasher import has_content_changed


def test_has_content_changed_returns_false_for_identical_hashes():
    assert has_content_changed("abc123", "abc123") is False


def test_has_content_changed_returns_true_for_different_hashes():
    assert has_content_changed("abc123", "def456") is True
