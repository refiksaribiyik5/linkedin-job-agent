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

BILINEN SINIRLAMA (M3.1/M3.2/M3.3'un ayni dipnotu burada da gecerlidir, M10.2'de
canli olarak dogrulanip duzeltildi): asagidaki secicilerin (`_TITLE_SELECTOR`
vb.) ESKI hali dogrudan LinkedIn'in kendi CSS sinif adlarini hedefliyordu ve
CANLI olarak dogrulanamamisti - M10.2'nin ilk gercek calistirmasi bunun
LinkedIn'in artik hash'lenmis, anlamsiz sinif adlari kullandigini (dolayisiyla
`jobs_collected=0` uretti) ortaya cikardi. Duzeltme, LinkedIn'in DOM'una
dogrudan bagimliligi TAMAMEN kaldirir: bu secicilerin GUNCEL hali, BIZIM
`adapters/linkedin/playwright_client.py`'de tanimladigimiz kararli
`data-field` semasini hedefler (bkz. o modulun "Mimari sinir" notu) -
LinkedIn'in kendi HTML'i artik bu dosyaya HICBIR ZAMAN sizmaz.

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
from pydantic import BaseModel, ConfigDict, Field, model_validator

from linkedinbot.config.schema import TargetCriteria
from linkedinbot.errors import TransientError
from linkedinbot.ports.linkedin_port import LinkedInPort, SessionInvalidError
from linkedinbot.retry import retry_with_backoff

logger = logging.getLogger(__name__)

# M10.2 duzeltmesi: bu secicilerin ARTIK LinkedIn'in kendi (kirilgan, hash'li)
# DOM'una HICBIR bagimliligi yoktur - `adapters/linkedin/playwright_client.py`
# (bkz. o modulun "Mimari sinir" notu) LinkedIn'in ham HTML'ini asla buraya
# sizdirmaz, bunun yerine BIZIM tanimladigimiz bu kararli `data-field`
# semasina sahip sentetik bir HTML uretir. Bu dosya bu yuzden LinkedIn DOM'u
# yeniden degisse bile DEGISMEZ kalmalidir - butun oynaklik yukaridaki
# adaptor dosyasinda izole edilmistir.
_TITLE_SELECTOR = '[data-field="title"]'
_COMPANY_SELECTOR = '[data-field="company"]'
_LOCATION_SELECTOR = '[data-field="location"]'
_DATE_SELECTOR = '[data-field="date"]'
_DESCRIPTION_SELECTOR = '[data-field="description"]'
_LINK_SELECTOR = '[data-field="link"]'


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


class CollectionResult(BaseModel):
    """PaginationController'in ciktisi (Roadmap M9.4, "unified completeness"
    duzeltmesi - bagimsiz review sonrasi).

    Kapali-ilan tespiti (FR-10, diff_job_postings), `current_scan`'in TAM
    (eksiksiz) bir tarama oldugunu VARSAYAR - taranmayan herhangi bir
    sorgu/sayfa, o sorgunun ilanlarinin "artik gorulmedigi" icin YANLISLIKLA
    "kapandi" olarak yorumlanmasina yol acar. `is_complete`, bu varsayimin
    gecerli olup olmadigini temsil eden TEK, birlestirilmis alandir - "Toplama
    tam mi?" sorusunun dogrudan cevabidir. Varsayilan `True`dur (tam bir
    tarama). Onu `False` yapan UC BAGIMSIZ (ama birbirini DISLAMAYAN) sebep
    vardir - hepsi `RunOrchestrator`'in Run'i "Partial" isaretlemesi icin
    AYNI TEK alani (`is_complete`) okumasini saglar:

    1. `collection_capped=True` (FR-21 ust sinirina ulasildi) - FR-21'in
       kendi kabul kriteri bunu acikca "toplamanin KESILDIGI" olarak
       tanimlar (bkz. FR-21 metni: "...toplamayı durdurur ve bu durumu
       ...toplamanın kesildiğini... Run Log'da açıkça belirtir").
    2. Devre kesici-lite (Section 21) tetiklendi - ardisik basarisizlik
       sayisi esigi asti.
    3. Bir veya daha fazla sorgu TUM yeniden deneme denemelerini tuketti
       (ama devre kesici esigini ASMADAN, "basarisiz ama devam et" ile bir
       sonraki sorguya gecildi) - bu sorgunun ilanlari HICBIR ZAMAN
       BASARIYLA taranamadi, dolayisiyla taramanin geri kalani basarili
       olsa bile TAM degildir. (Bu, bagimsiz review'un buldugu ucuncu
       production hatasinin kok sebebiydi: bu durum ONCEDEN hicbir alanda
       izsiz kaliyordu.)

    `collection_capped` KENDI BASINA ayri bir alan olarak KALIR (FR-21'in
    "acikca belirtir" gereksinimi icin, "neden" bilgisini korumak amaciyla)
    ama artik `is_complete`ten BAGIMSIZ degildir: `collection_capped=True`
    HER ZAMAN `is_complete=False` anlamina gelir (asagidaki validator ile
    zorunlu kilinir).
    """

    model_config = ConfigDict(extra="forbid")

    raw_cards: list[str]
    collection_capped: bool = False
    is_complete: bool = True
    partial_reason: str | None = None

    @model_validator(mode="after")
    def _capped_implies_incomplete(self) -> CollectionResult:
        if self.collection_capped and self.is_complete:
            raise ValueError("collection_capped=True iken is_complete=True olamaz.")
        return self

    @model_validator(mode="after")
    def _incomplete_requires_a_reason(self) -> CollectionResult:
        if not self.is_complete and self.partial_reason is None:
            raise ValueError("is_complete=False iken partial_reason zorunludur.")
        if self.is_complete and self.partial_reason is not None:
            raise ValueError("is_complete=True iken partial_reason bos olmalidir.")
        return self


def _fetch_page_with_retry(
    linkedin_port: LinkedInPort,
    account_id: UUID,
    location: str,
    keywords: str,
    page: int,
    *,
    retry_attempts: int,
    retry_base_delay_ms: int,
    retry_max_delay_ms: int,
    sleep: Callable[[float], None],
) -> list[str]:
    """TEK bir sayfa/sorgu istegini `retry_with_backoff()` (retry.py, M9.4)
    ile sarmalar. `SessionInvalidError` (artik `PermanentError`, bkz.
    ports/linkedin_port.py) HICBIR ZAMAN `TransientError`'e cevrilmez -
    dogrudan, degistirilmeden yukari sizar (asla yeniden denenmez, FR-1).
    BASKA herhangi bir istisna (agi zaman asimi, Playwright hatasi vb.)
    `TransientError`e cevrilip yeniden deneme dongusune sokulur.
    """

    def _fetch() -> list[str]:
        try:
            return linkedin_port.search_jobs_page(account_id, location, keywords, page)
        except SessionInvalidError:
            raise
        except Exception as exc:
            raise TransientError(str(exc)) from exc

    return retry_with_backoff(
        _fetch,
        max_attempts=retry_attempts,
        base_delay_ms=retry_base_delay_ms,
        max_delay_ms=retry_max_delay_ms,
        sleep=sleep,
    )


def collect_raw_job_cards(
    linkedin_port: LinkedInPort,
    account_id: UUID,
    target_criteria: TargetCriteria,
    max_jobs_per_run: int,
    delay_seconds: float,
    jitter_seconds: float,
    linkedin_retry_attempts: int,
    retry_base_delay_ms: int,
    retry_max_delay_ms: int,
    linkedin_consecutive_failure_threshold: int,
    sleep: Callable[[float], None] = time.sleep,
) -> CollectionResult:
    """PaginationController: `target_criteria`'daki her (lokasyon, departman
    kumesi) cifti icin `linkedin_port.search_jobs_page`'i sayfa sayfa
    cagirir, `max_jobs_per_run`'a (FR-21) ulasilana veya butun sorgular
    dogal olarak tukeninceye kadar (bos sayfa donene kadar) devam eder.

    RateLimiter (M3.5): ILK istek HARIC, `linkedin_port.search_jobs_page()`'e
    yapilan HER cagridan once `_apply_rate_limit()` ile beklenir - hem
    AYRI sorgular (farkli lokasyon/departman) hem de AYNI sorgunun ardisik
    sayfalari arasinda, cunku ikisi de gercek birer LinkedIn istegidir.

    Retry + Devre Kesici (M9.4, TDD Section 21): her istek
    `_fetch_page_with_retry()` araciligiyla `linkedin_retry_attempts`'e
    kadar yeniden denenir. Bir sorgunun TUM denemeleri tukenirse, ardisik
    basarisizlik sayaci artirilir ve "basarisiz ama devam et" ile bir
    sonraki sorguya gecilir - AYNI dogal-bos-sayfa sonlanmasi davranisi.
    HERHANGI bir basarili istek (bos sayfa DAHIL, cunku bu da GECERLI bir
    LinkedIn yanitidir) bu sayaci SIFIRLAR. Sayac
    `linkedin_consecutive_failure_threshold`'u asarsa, toplama HEMEN durur
    ve `is_complete=False` ile doner.

    Doner: `CollectionResult` - `collection_capped`, yalnizca `max_jobs_per_run`
    sinirina ulasildigi icin ERKEN durulduysa `True`'dur (Roadmap M3.3
    "Beklenen Sonuc"). `is_complete`, ASAGIDAKI UC sebepten HERHANGI biri
    gerceklestiyse `False`'dur (M9.4, "unified completeness" duzeltmesi):
    devre kesici tetiklendi, `max_jobs_per_run` sinirina ulasildi (yani
    `collection_capped=True`), veya bir ya da daha fazla sorgu TUM yeniden
    deneme denemelerini devre kesici esigine ulasmadan tuketti ("basarisiz
    ama devam et").
    """
    collected: list[str] = []

    if max_jobs_per_run <= 0:
        return CollectionResult(
            raw_cards=collected,
            collection_capped=True,
            is_complete=False,
            partial_reason=(
                f"Toplama sinirina (max_jobs_per_run={max_jobs_per_run}) hicbir "
                "sorgu calistirilmadan ulasildi."
            ),
        )

    is_first_request = True
    consecutive_failures = 0
    any_query_failed = False
    for location in target_criteria.locations:
        for titles in target_criteria.departments.values():
            keywords = _build_search_keywords(titles)
            page = 0
            while True:
                if not is_first_request:
                    _apply_rate_limit(sleep, delay_seconds, jitter_seconds)
                is_first_request = False

                try:
                    cards = _fetch_page_with_retry(
                        linkedin_port,
                        account_id,
                        location,
                        keywords,
                        page,
                        retry_attempts=linkedin_retry_attempts,
                        retry_base_delay_ms=retry_base_delay_ms,
                        retry_max_delay_ms=retry_max_delay_ms,
                        sleep=sleep,
                    )
                except TransientError:
                    any_query_failed = True
                    consecutive_failures += 1
                    if consecutive_failures >= linkedin_consecutive_failure_threshold:
                        return CollectionResult(
                            raw_cards=collected,
                            collection_capped=False,
                            is_complete=False,
                            partial_reason=(
                                f"Devre kesici tetiklendi: {consecutive_failures} ardisik "
                                "LinkedIn hatasi (esik: "
                                f"{linkedin_consecutive_failure_threshold})."
                            ),
                        )
                    break  # bu sorgu icin "basarisiz ama devam et" (RISK-2)

                consecutive_failures = 0
                if not cards:
                    break
                for card in cards:
                    collected.append(card)
                    if len(collected) >= max_jobs_per_run:
                        return CollectionResult(
                            raw_cards=collected,
                            collection_capped=True,
                            is_complete=False,
                            partial_reason=(
                                f"Toplama sinirina (max_jobs_per_run={max_jobs_per_run}) "
                                "ulasildigi icin toplama kesildi - bazi sorgular/sayfalar hic "
                                "denenmedi."
                            ),
                        )
                page += 1

    if any_query_failed:
        return CollectionResult(
            raw_cards=collected,
            collection_capped=False,
            is_complete=False,
            partial_reason=(
                "Bir veya daha fazla sorgu, devre kesici esigine ulasilmadan tum "
                "yeniden deneme denemelerini tuketti - bu sorgu(lar) hicbir zaman "
                "basariyla taranamadi."
            ),
        )
    return CollectionResult(raw_cards=collected)


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
