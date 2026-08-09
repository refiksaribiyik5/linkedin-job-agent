"""SearchClient + PaginationController (Roadmap M3.3, FR-21) + RecordExtractor
(Roadmap M3.4, FR-2) + RateLimiter (Roadmap M3.5, TDD Section 22).

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

M3.4 (RecordExtractor, FR-2) `extract_record()`/`extract_records()`'i ekler:
`collect_raw_job_cards()`'in urettigi ham HTML dizelerinden FR-2'nin
minimum alan setini (baslik, sirket, lokasyon, tarih, aciklama, link)
cikarir. Bu, `collect_raw_job_cards()`'tan AYRI, sonraki bir adimdir -
proje talimatiyla acikca onaylandigi gibi M3.3'un fonksiyonu/imzasi
KASITLI OLARAK degistirilmez. Bir kartin cikarimi basarisiz olursa
(gerekli bir alan bulunamaz/bos ise) `PartialRecordError` firlatilir;
`extract_records()` bunu YAKALAYIP LOGLAR ve o karti ATLAYIP diger
kartlarin islenmesine DEVAM EDER (Roadmap M3.4 "Beklenen Sonuc" -
tek bir bozuk kayit calistirmayi durdurmaz).

HTML ayristirma icin BeautifulSoup (M3.4, proje talimatiyla acikca
onaylandi) kullanilir - Python'in kendi yerlesik `html.parser`i backend
olarak yeterlidir, ek bir ayristirici (orn. lxml) KASITLI OLARAK
eklenmemistir (talimat: "yalnizca RecordExtractor icin gereken minimum
bagimlilik").

BILINEN SINIRLAMA (M3.1/M3.2/M3.3'un ayni dipnotu burada da gecerlidir):
asagidaki CSS secicileri (`_TITLE_SELECTOR` vb.), LinkedIn'in GERCEK,
GUNCEL DOM yapisina karsi CANLI olarak dogrulanamamistir (bu ortamda
gercek bir LinkedIn hesabina/tarayiciya erisim yoktur). Bu, kullanicinin
gercek hesabina karsi manuel olarak dogrulanmasi gereken bir varsayimdir.

M3.5 (RateLimiter, TDD Section 22) `_apply_rate_limit()`'i ekler ve
`collect_raw_job_cards()`'in kendi istek dongusune baglar: `linkedin_port.search_jobs_page()`'e
yapilan HER cagridan ONCE (akisin ILK istegi HARIC - ondan once "beklenecek"
bir onceki istek yoktur), sabit bir gecikmeye (`delay_seconds`) simetrik
bir zamanlama sapmasi (`jitter_seconds`) eklenerek uyunur. Bu, TDD Section
22'nin "İstekler arası... Sabit gecikme + jitter" ifadesinin BIREBIR
karsiligidir - Section 14/NFR-14'un CALISTIRMA-seviyesi (iki ayri Run
tetiklemesi ARASINDAKI, `Schedule.jitter_minutes`) jitter'i ile
KARISTIRILMAMALIDIR; bu, AYNI calistirma icindeki ARDISIK LinkedIn
ISTEKLERI arasindaki gecikmedir.

Proje talimatiyla acikca onaylanan tasarim karari: `delay_seconds`,
`jitter_seconds` ve `sleep`, `max_jobs_per_run`'un KENDI ONAYLANMIS
deseniyle (M3.3) AYNI sekilde `collect_raw_job_cards()`'a DUZ FONKSIYON
PARAMETRELERI olarak verilir - `config/schema.py`'ye (M3.5'in "Oluşturulacak
Dosyalar" listesinde acikca YER ALMAYAN bir dosya) HICBIR SEKILDE
dokunulmaz. "Configure edilebilirlik," bu mekanizma-seviyesi parametreleri
kabul etmesiyle saglanir; GERCEK degerin nereden (sabit bir varsayilan mi,
gelecekte bir config alani mi) geldigine cagiran (henuz insa edilmemis bir
Orchestrator, M9) karar verir. `sleep`'in varsayilani GERCEK `time.sleep`'tir
(guvenli varsayilan - hiz sinirlamasi ACIKCA devre disi birakilmadikca
HER ZAMAN calisir); test'lerde sahte/kaydedici bir `sleep` enjekte edilerek
gercek bekleme suresi olmadan davranis dogrulanir.

TDD Section 22'nin "tek eszamanli oturum, paralel tarayici ornegi yok"
gereksinimi, M1-M3.4'un zaten kurdugu mimari tarafindan KARSILANMISTIR -
`collect_raw_job_cards()` (ve butun collection/adapters.linkedin katmani)
hicbir zaman thread/async/multiprocessing kullanmaz; bu M3.5'in YENI bir
sey EKLEMESI gereken bir madde degildir, zaten mevcut, degismeyen bir
mimari ozelliktir.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from uuid import UUID

from bs4 import BeautifulSoup
from bs4.element import Tag
from pydantic import BaseModel, ConfigDict, Field

from linkedinbot.config.schema import TargetCriteria
from linkedinbot.ports.linkedin_port import LinkedInPort

logger = logging.getLogger(__name__)

_TITLE_SELECTOR = ".job-card-title"
_COMPANY_SELECTOR = ".job-card-company"
_LOCATION_SELECTOR = ".job-card-location"
_DATE_SELECTOR = ".job-card-date"
_DESCRIPTION_SELECTOR = ".job-card-description"
_LINK_SELECTOR = "a.job-card-link"


def _build_search_keywords(titles: list[str]) -> str:
    """SearchClient'in sorgu-kurma sorumlulugu: bir departman kumesinin
    ornek unvanlarini, LinkedIn'in bool arama sozdiziminde tek bir genis
    sorguya (tirnak icinde " OR " ile birlestirilmis) donusturur."""
    return " OR ".join(f'"{title}"' for title in titles)


def _apply_rate_limit(
    sleep: Callable[[float], None], delay_seconds: float, jitter_seconds: float
) -> None:
    """RateLimiter: sabit bir gecikmeye simetrik bir zamanlama sapmasi
    (jitter) ekleyip `sleep()` ile bekler (TDD Section 22 "Sabit gecikme
    + jitter"). Hesaplanan sure hicbir zaman negatif olamaz - `jitter_seconds`,
    `delay_seconds`'tan buyuk olsa bile `sleep()`'e her zaman `>= 0` bir
    deger verilir.
    """
    # S311 (bandit "kriptografik olmayan RNG") burada bir yanlis-pozitiftir:
    # bu jitter, istekler arasi zamanlamayi hafifce degistiren bir bot-
    # vatandasligi onlemidir (TDD Section 22) - guvenlik/kriptografi ile
    # ilgisi yoktur, `secrets` modulu burada yanlis arac olurdu.
    jittered_delay = delay_seconds + random.uniform(-jitter_seconds, jitter_seconds)  # noqa: S311
    sleep(max(0.0, jittered_delay))


def collect_raw_job_cards(
    linkedin_port: LinkedInPort,
    account_id: UUID,
    target_criteria: TargetCriteria,
    max_jobs_per_run: int,
    delay_seconds: float,
    jitter_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[list[str], bool]:
    """PaginationController: `target_criteria`'daki her (lokasyon, departman
    kumesi) cifti icin `linkedin_port.search_jobs_page`'i sayfa sayfa
    cagirir, `max_jobs_per_run`'a (FR-21) ulasilana veya butun sorgular
    dogal olarak tukeninceye kadar (bos sayfa donene kadar) devam eder.

    RateLimiter (M3.5): ILK istek HARIC, `linkedin_port.search_jobs_page()`'e
    yapilan HER cagridan once `_apply_rate_limit()` ile beklenir - hem
    AYRI sorgular (farkli lokasyon/departman) hem de AYNI sorgunun ardisik
    sayfalari arasinda, cunku ikisi de gercek birer LinkedIn istegidir.

    Doner: `(ham_ilan_kartlari, collection_capped)` - `collection_capped`
    yalnizca sinira ulasildigi icin ERKEN durulduysa `True`'dur; tum
    sorgular kendiliginden tukendiyse `False`'tur (Roadmap M3.3 "Beklenen
    Sonuc").
    """
    collected: list[str] = []

    if max_jobs_per_run <= 0:
        return collected, True

    is_first_request = True
    for location in target_criteria.locations:
        for titles in target_criteria.departments.values():
            keywords = _build_search_keywords(titles)
            page = 0
            while True:
                if not is_first_request:
                    _apply_rate_limit(sleep, delay_seconds, jitter_seconds)
                is_first_request = False

                cards = linkedin_port.search_jobs_page(account_id, location, keywords, page)
                if not cards:
                    break
                for card in cards:
                    collected.append(card)
                    if len(collected) >= max_jobs_per_run:
                        return collected, True
                page += 1

    return collected, False


class PartialRecordError(Exception):
    """Bir ilan kartindan FR-2'nin minimum alan setinden biri (baslik,
    sirket, lokasyon, tarih, aciklama, link) cikarilamadi - bulunamadi
    veya bos. Bu KART atlanir; akis (diger kartlarin islenmesi) durmaz
    (Roadmap M3.4 "Beklenen Sonuc")."""


class RawJobRecord(BaseModel):
    """FR-2'nin minimum alan seti - `target_criteria.departments` gibi
    daha genis bir Job Posting semasi (PRD Section 15.2) DEGIL, yalnizca
    M3.4'un kendi "Amaç"inin acikca sinirladigi alt kume. Tum alanlar HAM
    (ayristirilmamis) metin degerleridir - gercek tarih/URL dogrulamasi
    Normalizasyon'un (daha sonraki bir milestone) isidir."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    location: str = Field(min_length=1)
    posted_date: str = Field(min_length=1)
    description: str = Field(min_length=1)
    link: str = Field(min_length=1)


def _extract_text(card: Tag, selector: str, field_name: str) -> str:
    element = card.select_one(selector)
    if element is None:
        raise PartialRecordError(f"'{field_name}' alani bulunamadi (secici: {selector!r}).")
    text = element.get_text(strip=True)
    if not text:
        raise PartialRecordError(f"'{field_name}' alani bos (secici: {selector!r}).")
    return text


def _extract_link(card: Tag, selector: str) -> str:
    element = card.select_one(selector)
    href = element.get("href") if element is not None else None
    if not href:
        raise PartialRecordError(f"'link' alani bulunamadi (secici: {selector!r}).")
    return str(href)


def extract_record(raw_html: str) -> RawJobRecord:
    """Tek bir ham ilan karti HTML'sinden FR-2'nin minimum alan setini
    cikarir. Herhangi bir alan bulunamazsa veya bossa `PartialRecordError`
    firlatir - cagiran (`extract_records()`) bunu yakalayip karti atlar.

    TDD Section 20, `PartialRecordError`'i genis bir sekilde "Tek bir ilan
    kaydinin ayristirilamamasi" olarak tanimlar - yalnizca "eksik/bos
    zorunlu alan" ile sinirli degildir. Bu yuzden ayristirma sirasinda
    (BeautifulSoup'un kendisi veya secici degerlendirmesi) beklenmedik
    herhangi baska bir hata olusursa da, bu KASITLI OLARAK `PartialRecordError`'a
    donusturulur (ozgun hata `from exc` ile zincirlenerek) - boylece tek
    bir kartin ayristirilmasindaki HERHANGI bir hata, `extract_records()`'in
    diger kartlarin islenmesine devam etmesini engellemez (Roadmap M3.4
    "...ve Kismi Hata Toleransi").
    """
    try:
        card = BeautifulSoup(raw_html, "html.parser")
        return RawJobRecord(
            title=_extract_text(card, _TITLE_SELECTOR, "title"),
            company=_extract_text(card, _COMPANY_SELECTOR, "company"),
            location=_extract_text(card, _LOCATION_SELECTOR, "location"),
            posted_date=_extract_text(card, _DATE_SELECTOR, "posted_date"),
            description=_extract_text(card, _DESCRIPTION_SELECTOR, "description"),
            link=_extract_link(card, _LINK_SELECTOR),
        )
    except PartialRecordError:
        raise
    except Exception as exc:
        raise PartialRecordError(f"Ilan karti ayristirilamadi: {exc}") from exc


def extract_records(raw_cards: list[str]) -> list[RawJobRecord]:
    """RecordExtractor: `collect_raw_job_cards()`'in urettigi ham HTML
    dizelerinin HER birini `extract_record()` ile isler. Bir kartin
    cikarimi basarisiz olursa (`PartialRecordError`), o kart LOGLANIR ve
    ATLANIR; diger kartlarin islenmesi DEVAM EDER (Roadmap M3.4 "Beklenen
    Sonuc" - tek bir bozuk kayit akisi durdurmaz).
    """
    records: list[RawJobRecord] = []
    for raw_html in raw_cards:
        try:
            records.append(extract_record(raw_html))
        except PartialRecordError as exc:
            logger.warning("Ilan karti atlandi (PartialRecordError): %s", exc)
    return records
