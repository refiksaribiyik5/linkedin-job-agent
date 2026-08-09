"""Content Hash karsilastirma yardimcisi (Roadmap M4.2).

Hash HESAPLAMA mantigi ZATEN M4.1'in (`normalization.normalizer.compute_content_hash`)
sorumlulugudur - bu modul onu TEKRARLAMAZ. Diff Engine'in (M4.2) ihtiyaci
olan tek sey, iki ZATEN hesaplanmis hash'i karsilastirmaktir (FR-14
"anlamli degisiklik" tespiti); bu modul o TEK islemi izole eder.
"""

from __future__ import annotations


def has_content_changed(previous_hash: str, current_hash: str) -> bool:
    """Iki content_hash farkliysa `True` doner (FR-14: anlamli bir
    degisiklik var). Hash'lerin KENDISI zaten yalnizca FR-14 kapsamindaki
    alanlardan (Title/Location/Workplace Type/Description) hesaplandigi
    icin (bkz. M4.1), bu karsilastirma dogrudan/basit bir esitlik
    kontroludur - oynak alanlar zaten hash'e dahil edilmemistir.
    """
    return previous_hash != current_hash
