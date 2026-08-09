"""Location Filter - FR-3, PRD Section 11.1, EDGE-3 (Roadmap M6.2).

`filter_by_location.py`, `blacklist_filter.py` (M6.1) ile ayni SAF
fonksiyon desenini izler: hicbir repository/DB'ye erismez, LLM Gateway'e
ihtiyac duymaz (Section 11.4: Location, Blacklist gibi ucuz/ikili bir
kontroldur, semantik/AI degerlendirmesi Department'a - M6.4 - ozeldir).

`target_locations` dogrudan bir parametredir - CLAUDE.md'nin acikca
belirttigi "target location(s)... must live in human-readable config,
never hardcoded" kurali geregi "Istanbul" hicbir yerde sabit-kodlanmaz
(M6.1'in `Preferences` parametresiyle ayni yaklasim: cagiran taraf, bu
listeyi runtime'da nereden (TargetCriteria.locations, M2.1) getirecegini
bilir - bu modulun kendisi config semasina bagimli degildir).

**Belirsizlik (EDGE-3) cozumu - neden `workplace_type`'a dayanir:**
On-site/Hybrid bir ilan HER ZAMAN gercek, fiziksel bir ofis lokasyonu
belirtir - bu yuzden hedef listede degilse KESIN olarak reddedilir
(sehir bilgisi zaten mevcuttur, belirsizlik yoktur). Yalnizca Remote (ya
da workplace_type hic belirtilmemis, orn. eksik/eski taranmis veri) bir
ilan, sirket/pozisyonun gercekte nerede oldugunu ORTAYA KOYMAYABILIR -
PRD 11.1: "Uzaktan (Remote) veya hibrit ilanlar, sirketin/pozisyonun
Istanbul merkezli olmasi durumunda tercih edilir" (yani Istanbul
belirtilmiyorsa tercih EDILMEZ) ve EDGE-3'un tam da bu ornegi ("Uzaktan
ilan, hicbir sehir/ulke bilgisi icermiyor") vermesiyle birebir tutarlidir.
Bu ayrim, herhangi bir sehir-listesi veya virgul-ayristirma sezgisi ICAT
ETMEDEN (byle bir sezgi, bu ortamda dogrulanamayan gercek LinkedIn
lokasyon-dizesi bicimleri hakkinda tahmin gerektirirdi), yalnizca
JobPosting'in zaten var olan `workplace_type` alanindan turer.

EDGE-3: "Varsayilan olarak dislanir; ayri bir 'Location Unclear'
alaninda isaretlenir, sessizce silinmez." `FilterResult` (M1.1) bu
milestone'da DEGISTIRILMEDIGI icin (yeni bir alan eklenmez), bu isaretleme
`reason` metninin kendisi icinde acikca taninabilir bir "Location
Unclear" ibaresiyle yapilir - M6.1'in `blacklist_filter.py`'de zaten
kullandigi ayni "anlami `reason` dizesine kodla" yaklasimi.

`confidence` alani her zaman `None` birakilir - Blacklist gibi Location
da ikili/deterministik bir karardir (bkz. blacklist_filter.py'nin ayni
gerekcesi).

Self-review'de bulunan gercek kusur duzeltmesi: Python'in yerlesik
`str.lower()`'i, Turkce noktali buyuk harf "İ"yi ASCII "i" yerine "i" +
BIRLESIK NOKTA (U+0307) ikilisine cevirir (Turkce'ye ozgu, yerel-ayara
duyarli olmayan varsayilan Unicode kucuk harfe cevirme kurali) - bu
yuzden dogru yazilmis Turkce "İstanbul" (LinkedIn'in Turkce arayuzunde
beklenen yazim), naif bir `.lower()` karsilastirmasiyla ASCII "istanbul"
hedefiyle ESLESMEZ (yanlis negatif). `_fold_turkish_case()`, "İ"/"ı"yi
`.lower()`'dan ONCE ASCII "I"/"i"ye cevirerek bunu duzeltir.
"""

from __future__ import annotations

from linkedinbot.domain.evaluated_job import FilterResult
from linkedinbot.domain.job_posting import JobPosting, WorkplaceType

_LOCATION_AMBIGUOUS_WORKPLACE_TYPES = (None, WorkplaceType.REMOTE)


def _fold_turkish_case(text: str) -> str:
    return text.replace("İ", "I").replace("ı", "i").lower()


def filter_by_location(job_posting: JobPosting, target_locations: list[str]) -> FilterResult:
    location_lower = _fold_turkish_case(job_posting.location)
    matches_target = any(
        _fold_turkish_case(target) in location_lower for target in target_locations
    )

    if matches_target:
        return FilterResult(
            passed=True,
            reason=f"Location '{job_posting.location}' matches a target location.",
        )

    if job_posting.workplace_type in _LOCATION_AMBIGUOUS_WORKPLACE_TYPES:
        return FilterResult(
            passed=False,
            reason=(
                f"Location Unclear: '{job_posting.location}' does not indicate whether "
                "this remote/unspecified-workplace posting is tied to a target location."
            ),
        )

    return FilterResult(
        passed=False,
        reason=f"Location '{job_posting.location}' is outside the target locations.",
    )
