"""Paylasilan hata taksonomisi (TDD Section 20, Roadmap M9.4).

**Neden ayri, ust-duzey bir modul (`retry.py`'nin ICINDE degil):**
`TransientError`/`PermanentError`, uygulama capinda paylasilan bir
siniflandirmadir - `retry.py`'nin `retry_with_backoff()`'u bu ikiliden
YALNIZCA BIRINI (TransientError) tuketen TEK bir kullanicidir, sahibi
degildir. `ports/linkedin_port.py`'nin `SessionInvalidError`'i (M3.2)
`PermanentError`'dan turetilir ama `retry_with_backoff()`'u hicbir zaman
cagirmaz - taksonomi `retry.py` icinde tanimlansaydi, bu tur tuketiciler
yalnizca BIR istisna sinifina erismek icin butun geri-cekilme mekanizmasini
ice aktarmak zorunda kalirdi (sahiplik ters-donuklugu).

Bu modul, `domain/`'in aksine (yalnizca Section 15 varliklarinin Pydantic
modellerini tasir), saf Python istisna siniflarindan olusur - hicbir
model/is mantigi icermez. Sifir bagimliligi vardir; `ports/`, `collection/`,
`adapters/llm/` ve `retry.py` dahil HERHANGI bir katman tarafindan
guvenle ice aktarilabilir (import-linter'in ucuncu kontrati - "Domain
katmani db katmanini import edemez" - dahil hicbir mevcut kontratla
CATISMAZ, cunku bu modul ne domain ne de db katmanindadir).

**Taksonomi (TDD Section 20 tablosu):**
- `TransientError` - agi zaman asimi, LLM 429/5xx, gecici DB baglanti
  hatasi gibi GECICI hatalar. Retry mekanizmasina girer (bkz. retry.py).
- `PermanentError` - gecersiz oturum (FR-1), sema disi config (EDGE-15),
  LinkedIn yapisal degisikligi nedeniyle ayristirilamayan sayfa gibi
  KALICI hatalar. Retry edilmez; Run "Failed" olarak sonlanir.

Ikisi de BIRBIRINDEN BAGIMSIZ, dogrudan `Exception`'dan tureyen kardes
siniflardir - biri digerinin alt sinifi degildir (bir `except
TransientError` bloğu yanlislikla bir `PermanentError`'i da
yakalamamalidir).

`PartialRecordError` (M3.4, `collection/collector.py`) bu modulde
TANIMLANMAZ/TASINMAZ: o, TEK bir ilan kaydinin ayristirilamamasi icin
"atla ve logla" davranisi tasiyan, kendi basina, ASLA yeniden denenmeyen
farkli bir mekanizmadir - bu paylasilan retry taksonomisinin bir
tuketicisi degildir.
"""

from __future__ import annotations


class TransientError(Exception):
    """Gecici bir hata - retry mekanizmasina girer (TDD Section 20)."""


class PermanentError(Exception):
    """Kalici bir hata - retry edilmez, Run "Failed" olarak sonlanir
    (TDD Section 20)."""
