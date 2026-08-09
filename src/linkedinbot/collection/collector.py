"""SearchClient + PaginationController (Roadmap M3.3, FR-21).

TDD Section 6 modul sorumluluklari tablosu: `collection` modulu "Section 17
Target Location(s)/Departments kapsaminda arama sorgulari uretir,
`linkedin_port` uzerinden sonuclari ceker, FR-21 ust sinirini uygular, ham
RawJobRecord akisi uretir" ve TEK bagimliligi `linkedin_port`dir. Bu modul
Playwright'i HICBIR ZAMAN dogrudan import ETMEZ (proje talimatiyla acikca
onaylanan mimari karar) - butun tarayici detaylari `adapters.linkedin`
katmaninin arkasinda kalir (bkz. `LinkedInPort.search_jobs_page`, M3.3).

Anahtar kelime kurgusu (proje talimatiyla acikca onaylandi, Roadmap M3.3'un
"lokasyon/anahtar kelimelerle arama" ile TDD Section 9'un SearchClient
tanimini birlestirir): `target_criteria.departments`'teki HER departman
kumesi icin, o kumenin ornek unvanlari tirnak icinde " OR " ile
birlestirilerek TEK bir LinkedIn arama sorgusu olusturulur; bu, HER
(lokasyon, departman kumesi) cifti icin AYRI bir arama anlamina gelir.
Departman TAKSONOMISI (target_criteria.departments) burada yalnizca genis
bir arama agi olusturmak icin kullanilir - kesin semantik departman
eslestirmesi (PRD Section 11.2, LLM tabanli guven skoru) daha SONRAKI bir
pipeline adiminin (Filtreleme, M3.3 kapsami disinda) isidir.

FR-21 (`max_jobs_per_run`) siniri, TUM (lokasyon, departman) sorgulari ve
TUM sayfalar boyunca KUMULATIF olarak uygulanir - tek bir sorgu/sayfa
basina degil. Sinira ulasildigi anda (bir sayfanin ORTASINDA bile olsa)
toplama HEMEN durur ve fazladan hicbir sorgu/sayfa istenmez.

Alan cikarimi (RecordExtractor, ham HTML'den baslik/sirket/lokasyon/tarih/
aciklama/link cikarma) KASITLI OLARAK burada YOKTUR - bu Roadmap M3.4'un
scope'udur. Bu modul yalnizca ham ilan karti HTML dizeleri dondurur.
Istekler arasi gecikme/jitter (RateLimiter) de KASITLI OLARAK burada
YOKTUR - bu Roadmap M3.5'in scope'udur.
"""

from __future__ import annotations

from uuid import UUID

from linkedinbot.config.schema import TargetCriteria
from linkedinbot.ports.linkedin_port import LinkedInPort


def _build_search_keywords(titles: list[str]) -> str:
    """SearchClient'in sorgu-kurma sorumlulugu: bir departman kumesinin
    ornek unvanlarini, LinkedIn'in bool arama sozdiziminde tek bir genis
    sorguya (tirnak icinde " OR " ile birlestirilmis) donusturur."""
    return " OR ".join(f'"{title}"' for title in titles)


def collect_raw_job_cards(
    linkedin_port: LinkedInPort,
    account_id: UUID,
    target_criteria: TargetCriteria,
    max_jobs_per_run: int,
) -> tuple[list[str], bool]:
    """PaginationController: `target_criteria`'daki her (lokasyon, departman
    kumesi) cifti icin `linkedin_port.search_jobs_page`'i sayfa sayfa
    cagirir, `max_jobs_per_run`'a (FR-21) ulasilana veya butun sorgular
    dogal olarak tukeninceye kadar (bos sayfa donene kadar) devam eder.

    Doner: `(ham_ilan_kartlari, collection_capped)` - `collection_capped`
    yalnizca sinira ulasildigi icin ERKEN durulduysa `True`'dur; tum
    sorgular kendiliginden tukendiyse `False`'tur (Roadmap M3.3 "Beklenen
    Sonuc").
    """
    collected: list[str] = []

    if max_jobs_per_run <= 0:
        return collected, True

    for location in target_criteria.locations:
        for titles in target_criteria.departments.values():
            keywords = _build_search_keywords(titles)
            page = 0
            while True:
                cards = linkedin_port.search_jobs_page(account_id, location, keywords, page)
                if not cards:
                    break
                for card in cards:
                    collected.append(card)
                    if len(collected) >= max_jobs_per_run:
                        return collected, True
                page += 1

    return collected, False
