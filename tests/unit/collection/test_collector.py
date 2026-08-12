"""collection/collector.py icin birim testleri (Roadmap M3.3, FR-21; M3.4,
FR-2; M3.5, TDD Section 22).

Roadmap M3.3 "Beklenen Sonuc": "Gecerli bir oturum ve config ile, sinirli
sayida ham arama sonucu doner; sinira ulasilirsa collection_capped=true
isaretlenir." Bu testler, gercek Playwright'a hic dokunmadan (bkz.
test_playwright_client.py, tarayici tarafi zaten ayri test edildi), sahte
(in-memory) bir `LinkedInPort` implementasyonu uzerinden SearchClient +
PaginationController mantigini dogrular.

Proje talimatiyla acikca onaylanan mimari karar: `collector.py` `LinkedInPort`'a
BAGIMLIDIR, Playwright'a DEGIL - TDD Section 6'nin `collection` modulu icin
listeledigi tek bagimlilik (`linkedin_port`) budur.

Anahtar kelime kurgusu (proje talimatiyla acikca onaylandi): her (lokasyon,
departman kumesi) cifti icin AYRI bir LinkedIn aramasi yapilir; anahtar
kelimeler o kumenin ornek unvanlarinin tirnak icinde OR ile birlestirilmesiyle
olusturulur (orn. `"Sales" OR "Sales Executive"`). FR-21'in `max_jobs_per_run`
siniri, TUM bu aramalar boyunca KUMULATIF olarak uygulanir (tek bir arama
basina degil).

M3.5 (RateLimiter, TDD Section 22): `collect_raw_job_cards()` artik
`delay_seconds`/`jitter_seconds`/`sleep` parametrelerini alir (proje
talimatiyla acikca onaylandi: `max_jobs_per_run`'un KENDI ONCEDEN
ONAYLANMIS deseniyle AYNI - duz fonksiyon parametreleri, config semasina
DOKUNULMAZ). M3.3/M3.4'ten kalan testler, kendi test amaclariyla ILGISIZ
gercek bekleme sureleri eklememesi icin `delay_seconds=0, jitter_seconds=0,
sleep=_no_op_sleep` ile acikca guncellenir - bu, M3.5'in kendi ZORUNLU
kildigi bir imza degisikligi, gereksiz bir "calisiyor kodu yeniden
duzenleme" degildir.
"""

from __future__ import annotations

import logging
import time
from uuid import UUID, uuid4

import pytest
from bs4 import BeautifulSoup

from linkedinbot.collection import collector as module_under_test
from linkedinbot.collection.collector import (
    PartialRecordError,
    RawJobRecord,
    collect_raw_job_cards,
    extract_record,
    extract_records,
)
from linkedinbot.config.schema import TargetCriteria
from linkedinbot.ports.linkedin_port import LinkedInPort, SessionInvalidError

ACCOUNT_ID = uuid4()


def _no_op_sleep(seconds: float) -> None:
    """M3.3/M3.4'ten kalan, hiz sinirlamayla ILGISIZ testler icin - bu
    testlerin gercekten beklememesini saglar."""


def _recording_sleep():
    calls: list[float] = []

    def _sleep(seconds: float) -> None:
        calls.append(seconds)

    _sleep.calls = calls
    return _sleep


class _FakeLinkedInPort(LinkedInPort):
    """Sahte `LinkedInPort`: `search_jobs_page` cagrilarini kaydeder ve
    `pages_by_query`'de tanimlanan (location, keywords) -> sayfa listesi
    eslemesine gore ham kart listeleri doner. Tanimlanmamis bir sorgu veya
    `len(pages)` disindaki bir sayfa istegi bos liste (dogal sayfalama
    sonu) doner.

    `failures_before_success_by_query` (M9.4 eklentisi): verilen sorgu icin
    HER cagrida, sayac sifira inene kadar bir `RuntimeError` firlatir (retry
    mekanizmasini test etmek icin - collector.py bunu `TransientError`'e
    cevirip `retry_with_backoff()` araciligiyla yeniden dener). `always_fail_queries`
    ise o sorgu icin HER ZAMAN (retry tukeninceye kadar da) basarisiz olur -
    devre kesici senaryolarini test etmek icin.
    """

    def __init__(
        self,
        pages_by_query: dict[tuple[str, str], list[list[str]]] | None = None,
        failures_before_success_by_query: dict[tuple[str, str], int] | None = None,
        always_fail_queries: frozenset[tuple[str, str]] = frozenset(),
    ):
        self._pages_by_query = pages_by_query or {}
        self._failures_before_success_by_query = dict(failures_before_success_by_query or {})
        self._always_fail_queries = always_fail_queries
        self.calls: list[tuple[UUID, str, str, int]] = []

    def ensure_session(self, account_id: UUID) -> None:
        raise NotImplementedError("M3.3 testlerinde kullanilmaz")

    def validate(self, account_id: UUID) -> None:
        raise NotImplementedError("M3.3 testlerinde kullanilmaz")

    def search_jobs_page(
        self, account_id: UUID, location: str, keywords: str, page: int
    ) -> list[str]:
        self.calls.append((account_id, location, keywords, page))
        query = (location, keywords)
        if query in self._always_fail_queries:
            raise RuntimeError("simulated persistent LinkedIn failure")
        remaining_failures = self._failures_before_success_by_query.get(query, 0)
        if remaining_failures > 0:
            self._failures_before_success_by_query[query] = remaining_failures - 1
            raise RuntimeError("simulated transient LinkedIn failure")
        pages = self._pages_by_query.get(query)
        if pages is None or page >= len(pages):
            return []
        return pages[page]


def _target_criteria(**overrides) -> TargetCriteria:
    data = {
        "locations": ["Istanbul"],
        "departments": {"Sales & Business Development": ["Sales", "Sales Executive"]},
        "experience_levels": ["Entry Level"],
        "workplace_types": ["On-site"],
    }
    data.update(overrides)
    return TargetCriteria(**data)


def test_collect_raw_job_cards_builds_one_query_per_cluster_per_location():
    target_criteria = _target_criteria(
        locations=["Istanbul", "Ankara"],
        departments={
            "Sales & Business Development": ["Sales", "Sales Executive"],
            "Marketing": ["Marketing", "Digital Marketing"],
        },
    )
    port = _FakeLinkedInPort()

    collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=200,
        delay_seconds=0.0,
        jitter_seconds=0.0,
        linkedin_retry_attempts=3,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=5,
        sleep=_no_op_sleep,
    )

    queries = {(location, keywords) for _acc, location, keywords, _page in port.calls}
    assert queries == {
        ("Istanbul", '"Sales" OR "Sales Executive"'),
        ("Istanbul", '"Marketing" OR "Digital Marketing"'),
        ("Ankara", '"Sales" OR "Sales Executive"'),
        ("Ankara", '"Marketing" OR "Digital Marketing"'),
    }


def test_collect_raw_job_cards_keywords_are_quoted_and_or_joined():
    target_criteria = _target_criteria(
        departments={"Consulting": ["Consulting", "Management Consulting", "Business Consulting"]}
    )
    port = _FakeLinkedInPort()

    collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=200,
        delay_seconds=0.0,
        jitter_seconds=0.0,
        linkedin_retry_attempts=3,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=5,
        sleep=_no_op_sleep,
    )

    keywords_used = {keywords for _acc, _loc, keywords, _page in port.calls}
    assert keywords_used == {'"Consulting" OR "Management Consulting" OR "Business Consulting"'}


def test_collect_raw_job_cards_paginates_within_a_query_until_empty_page():
    target_criteria = _target_criteria()
    port = _FakeLinkedInPort(
        pages_by_query={
            ("Istanbul", '"Sales" OR "Sales Executive"'): [
                ["card-0-a", "card-0-b"],
                ["card-1-a"],
                # sayfa 2 tanimsiz -> bos donecek, sayfalama burada durur
            ],
        }
    )

    result = collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=200,
        delay_seconds=0.0,
        jitter_seconds=0.0,
        linkedin_retry_attempts=3,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=5,
        sleep=_no_op_sleep,
    )

    assert result.raw_cards == ["card-0-a", "card-0-b", "card-1-a"]
    assert result.collection_capped is False
    assert result.is_complete is True
    assert result.partial_reason is None
    pages_requested = [page for _acc, _loc, _kw, page in port.calls]
    assert pages_requested == [0, 1, 2]


def test_collect_raw_job_cards_stops_exactly_at_cap_mid_page():
    target_criteria = _target_criteria()
    port = _FakeLinkedInPort(
        pages_by_query={
            ("Istanbul", '"Sales" OR "Sales Executive"'): [
                ["card-1", "card-2", "card-3", "card-4", "card-5"],
            ],
        }
    )

    result = collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=3,
        delay_seconds=0.0,
        jitter_seconds=0.0,
        linkedin_retry_attempts=3,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=5,
        sleep=_no_op_sleep,
    )

    # Roadmap M3.3 "Tamamlanma Dogrulamasi": "tam olarak <=5 sonuc" -
    # sinira ulasildiginda sayfanin geri kalani dahil edilmemelidir.
    assert result.raw_cards == ["card-1", "card-2", "card-3"]
    assert result.collection_capped is True
    # M9.4 duzeltmesi (independent review, "unified completeness"): FR-21
    # bir capped calistirmayi acikca "kesildi" olarak tanimlar - bu, TAM
    # bir tarama DEGILDIR (kalan kartlar/sorgular hic denenmedi).
    assert result.is_complete is False
    assert result.partial_reason is not None


def test_collect_raw_job_cards_does_not_query_further_once_capped():
    target_criteria = _target_criteria(
        departments={
            "Sales & Business Development": ["Sales"],
            "Marketing": ["Marketing"],
        }
    )
    port = _FakeLinkedInPort(
        pages_by_query={
            ("Istanbul", '"Sales"'): [["card-1", "card-2", "card-3"]],
            ("Istanbul", '"Marketing"'): [["card-4"]],
        }
    )

    result = collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=2,
        delay_seconds=0.0,
        jitter_seconds=0.0,
        linkedin_retry_attempts=3,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=5,
        sleep=_no_op_sleep,
    )

    assert result.raw_cards == ["card-1", "card-2"]
    assert result.collection_capped is True
    assert result.is_complete is False
    # Sinira ilk sorguda ulasildigi icin ikinci departmanin sorgusu HIC
    # yapilmamali - FR-21'in "toplamayi durdurur" gereksinimi.
    assert all(keywords == '"Sales"' for _acc, _loc, keywords, _page in port.calls)


def test_collect_raw_job_cards_not_capped_when_naturally_exhausted_below_cap():
    target_criteria = _target_criteria()
    port = _FakeLinkedInPort(
        pages_by_query={
            ("Istanbul", '"Sales" OR "Sales Executive"'): [["card-1", "card-2"]],
        }
    )

    result = collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=200,
        delay_seconds=0.0,
        jitter_seconds=0.0,
        linkedin_retry_attempts=3,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=5,
        sleep=_no_op_sleep,
    )

    assert result.raw_cards == ["card-1", "card-2"]
    assert result.collection_capped is False


def test_collect_raw_job_cards_passes_account_id_through():
    target_criteria = _target_criteria()
    port = _FakeLinkedInPort()

    collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=200,
        delay_seconds=0.0,
        jitter_seconds=0.0,
        linkedin_retry_attempts=3,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=5,
        sleep=_no_op_sleep,
    )

    assert all(acc == ACCOUNT_ID for acc, _loc, _kw, _page in port.calls)


def test_collect_raw_job_cards_propagates_session_invalid_error():
    class _RaisingPort(_FakeLinkedInPort):
        def __init__(self):
            super().__init__()
            self.raise_count = 0

        def search_jobs_page(self, account_id, location, keywords, page):
            self.raise_count += 1
            raise SessionInvalidError("oturum gecersiz")

    target_criteria = _target_criteria()
    port = _RaisingPort()

    with pytest.raises(SessionInvalidError):
        collect_raw_job_cards(
            port,
            ACCOUNT_ID,
            target_criteria,
            max_jobs_per_run=200,
            delay_seconds=0.0,
            jitter_seconds=0.0,
            linkedin_retry_attempts=3,
            retry_base_delay_ms=0,
            retry_max_delay_ms=0,
            linkedin_consecutive_failure_threshold=5,
            sleep=_no_op_sleep,
        )

    # M9.4: SessionInvalidError PermanentError'dir - retry_with_backoff()
    # tarafindan HIC yakalanmaz, ilk cagrida derhal yukari sizar.
    assert port.raise_count == 1


def test_collect_raw_job_cards_zero_cap_collects_nothing_and_is_capped():
    # Sinir durum: max_jobs_per_run gecerli config semasinda gt=0 zorunlu
    # kilinsa da (bkz. config/schema.py CollectionLimits), collector'in
    # kendisi 0 (veya cok kucuk) bir sinirla cagrildiginda hicbir karti
    # toplamadan hemen capped=True dondurmelidir - hicbir arama sorgusu
    # gereksiz yere calistirilmamalidir.
    target_criteria = _target_criteria()
    port = _FakeLinkedInPort(
        pages_by_query={("Istanbul", '"Sales" OR "Sales Executive"'): [["card-1"]]}
    )

    result = collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=0,
        delay_seconds=0.0,
        jitter_seconds=0.0,
        linkedin_retry_attempts=3,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=5,
        sleep=_no_op_sleep,
    )

    assert result.raw_cards == []
    assert result.collection_capped is True
    assert result.is_complete is False
    assert port.calls == []


# ---------------------------------------------------------------------------
# Retry + Devre Kesici (Roadmap M9.4, TDD Section 21) - her sayfa/sorgu
# istegi, `TransientError`e cevrilen bir hata alirsa `retry_with_backoff()`
# (retry.py) araciligiyla yeniden denenir. Butun denemeler bir sorgu icin
# tukenirse (ama devre kesici ESIGI henuz asilmadiysa) o sorgu "basarisiz
# ama devam et" olarak ele alinir - dogal bos-sayfa sonlanmasi gibi toplamaya
# DEVAM EDILIR, ama bu sorgu HIC BASARIYLA taranamadigi icin artik tarama
# TAM (complete) sayilmaz: `CollectionResult.is_complete=False` doner (bagimsiz
# review, "unified completeness" duzeltmesi). Ardisik boyle basarisizliklarin
# sayisi `linkedin_consecutive_failure_threshold`'u asarsa, toplama HEMEN
# durur ve yine `is_complete=False` doner - her iki durumda da
# `RunOrchestrator`'in (M9.3) Run'i "Partial" isaretlemesi icin.
# ---------------------------------------------------------------------------


def test_collect_raw_job_cards_retries_a_transient_failure_and_recovers():
    target_criteria = _target_criteria()
    query = ("Istanbul", '"Sales" OR "Sales Executive"')
    port = _FakeLinkedInPort(
        pages_by_query={query: [["card-1"]]},
        failures_before_success_by_query={query: 2},
    )
    sleep = _recording_sleep()

    result = collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=200,
        delay_seconds=0.0,
        jitter_seconds=0.0,
        linkedin_retry_attempts=3,
        retry_base_delay_ms=10,
        retry_max_delay_ms=100,
        linkedin_consecutive_failure_threshold=5,
        sleep=sleep,
    )

    # 2 basarisizlik + 1 basari = sayfa 0 icin 3 cagri, sonra sayfa 1
    # (dogal bos sayfa) icin 1 cagri daha = toplam 4.
    assert result.raw_cards == ["card-1"]
    assert result.is_complete is True
    assert len(sleep.calls) >= 2  # en az iki geri cekilme beklemesi


def test_collect_raw_job_cards_exhausted_retries_below_threshold_continue_as_failed_but_continue():
    # Bir sorgunun TUM denemeleri tukenir (her zaman basarisiz olur), ama
    # devre kesici esigi (3) henuz asilmaz (yalnizca 1 ardisik basarisizlik) -
    # bu sorgu dogal bos-sayfa sonlanmasi gibi ele alinir, toplama DEVAM EDER
    # (Marketing sorgusu yine de calisir). AMA Sales sorgusu HIC BASARIYLA
    # taranamadigi icin (bagimsiz review, "unified completeness" duzeltmesi -
    # eski `is_partial`/`collection_capped` cifti bu durumda HICBIRINI True
    # yapmiyordu ve sessizce izsiz kaliyordu) toplam artik TAM sayilmaz.
    target_criteria = _target_criteria(
        departments={
            "Sales & Business Development": ["Sales"],
            "Marketing": ["Marketing"],
        }
    )
    port = _FakeLinkedInPort(
        pages_by_query={("Istanbul", '"Marketing"'): [["card-marketing"]]},
        always_fail_queries=frozenset({("Istanbul", '"Sales"')}),
    )
    sleep = _recording_sleep()

    result = collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=200,
        delay_seconds=0.0,
        jitter_seconds=0.0,
        linkedin_retry_attempts=2,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=3,
        sleep=sleep,
    )

    assert result.is_complete is False
    assert result.partial_reason is not None
    # Sales sorgusu tamamen basarisiz oldu ama ikinci (Marketing) sorgusu
    # yine de calistirildi ve karti toplandi.
    assert result.raw_cards == ["card-marketing"]


def test_collect_raw_job_cards_trips_circuit_breaker_and_returns_partial():
    target_criteria = _target_criteria(
        departments={
            "Sales & Business Development": ["Sales"],
            "Marketing": ["Marketing"],
            "Consulting": ["Consulting"],
        }
    )
    port = _FakeLinkedInPort(
        always_fail_queries=frozenset(
            {
                ("Istanbul", '"Sales"'),
                ("Istanbul", '"Marketing"'),
            }
        ),
        pages_by_query={("Istanbul", '"Consulting"'): [["card-consulting"]]},
    )
    sleep = _recording_sleep()

    result = collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=200,
        delay_seconds=0.0,
        jitter_seconds=0.0,
        linkedin_retry_attempts=1,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=2,
        sleep=sleep,
    )

    # Sales basarisiz (1. ardisik), Marketing basarisiz (2. ardisik ->
    # esik asildi) - toplama HEMEN durur, Consulting sorgusu HIC calismaz.
    assert result.is_complete is False
    assert result.partial_reason is not None
    assert "2" in result.partial_reason
    assert result.raw_cards == []
    queries_attempted = {(location, keywords) for _acc, location, keywords, _page in port.calls}
    assert ("Istanbul", '"Consulting"') not in queries_attempted


def test_collect_raw_job_cards_a_successful_request_resets_the_consecutive_failure_counter():
    # Devre kesici SADECE ARDISIK basarisizliklari sayar - Sales basarisiz
    # olur (1. ardisik), Marketing basarili olur (sayac SIFIRLANIR),
    # Consulting basarisiz olur (yeniden 1. ardisik, esik 2'yi GECMEZ) -
    # devre kesici HIC TETIKLENMEZ, UC sorgu da denenir (port.calls ile
    # asagida dogrulanir). Ama Sales VE Consulting sorgularinin HER IKISI
    # de basarisiz oldugu icin (bagimsiz review, "unified completeness"
    # duzeltmesi) toplam artik TAM sayilmaz.
    target_criteria = _target_criteria(
        departments={
            "Sales & Business Development": ["Sales"],
            "Marketing": ["Marketing"],
            "Consulting": ["Consulting"],
        }
    )
    port = _FakeLinkedInPort(
        always_fail_queries=frozenset(
            {
                ("Istanbul", '"Sales"'),
                ("Istanbul", '"Consulting"'),
            }
        ),
        pages_by_query={("Istanbul", '"Marketing"'): [["card-marketing"]]},
    )
    sleep = _recording_sleep()

    result = collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=200,
        delay_seconds=0.0,
        jitter_seconds=0.0,
        linkedin_retry_attempts=1,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=2,
        sleep=sleep,
    )

    assert result.is_complete is False
    assert result.raw_cards == ["card-marketing"]
    queries_attempted = {(location, keywords) for _acc, location, keywords, _page in port.calls}
    assert ("Istanbul", '"Consulting"') in queries_attempted


# ---------------------------------------------------------------------------
# RecordExtractor (Roadmap M3.4, FR-2) - her ham ilan karti HTML'sinden
# FR-2'nin minimum alan setini (baslik, sirket, lokasyon, tarih, aciklama,
# link) cikarir. Bozuk bir kart PartialRecordError olarak yakalanip
# atlanir; akis (diger kartlarin islenmesi) durmaz (Roadmap M3.4 "Beklenen
# Sonuc"). M3.3'un `collect_raw_job_cards()`'i KASITLI OLARAK degistirilmez
# (proje talimatiyla acikca onaylandi) - RecordExtractor, o fonksiyonun
# ciktisi (ham HTML dizeleri) uzerinde AYRI, sonraki bir adim olarak calisir.
# ---------------------------------------------------------------------------

WELL_FORMED_CARD = """
<div class="job-card-container">
  <h3 class="job-card-title">Sales Executive</h3>
  <span class="job-card-company">Acme Corp</span>
  <span class="job-card-location">Istanbul, Turkey</span>
  <time class="job-card-date">3 days ago</time>
  <p class="job-card-description">We are looking for a Sales Executive to join our team.</p>
  <a class="job-card-link" href="https://www.linkedin.com/jobs/view/12345">View</a>
</div>
"""


def _card_missing(field_class: str) -> str:
    """WELL_FORMED_CARD'in bir kopyasini, verilen alan sinifina sahip
    elemani tamamen kaldirarak uretir (o alanin HIC bulunamadigi durumu
    simule eder)."""
    soup = BeautifulSoup(WELL_FORMED_CARD, "html.parser")
    element = soup.select_one(f".{field_class}") or soup.select_one(field_class)
    if element is not None:
        element.decompose()
    return str(soup)


def test_extract_record_extracts_all_minimum_fields_from_well_formed_card():
    record = extract_record(WELL_FORMED_CARD)

    assert record == RawJobRecord(
        title="Sales Executive",
        company="Acme Corp",
        location="Istanbul, Turkey",
        posted_date="3 days ago",
        description="We are looking for a Sales Executive to join our team.",
        link="https://www.linkedin.com/jobs/view/12345",
    )


def test_extract_record_raises_partial_record_error_when_title_missing():
    with pytest.raises(PartialRecordError, match="title"):
        extract_record(_card_missing("job-card-title"))


def test_extract_record_raises_partial_record_error_when_company_missing():
    with pytest.raises(PartialRecordError, match="company"):
        extract_record(_card_missing("job-card-company"))


def test_extract_record_raises_partial_record_error_when_location_missing():
    with pytest.raises(PartialRecordError, match="location"):
        extract_record(_card_missing("job-card-location"))


def test_extract_record_raises_partial_record_error_when_date_missing():
    with pytest.raises(PartialRecordError, match="posted_date"):
        extract_record(_card_missing("job-card-date"))


def test_extract_record_raises_partial_record_error_when_description_missing():
    with pytest.raises(PartialRecordError, match="description"):
        extract_record(_card_missing("job-card-description"))


def test_extract_record_raises_partial_record_error_when_link_missing():
    with pytest.raises(PartialRecordError, match="link"):
        extract_record(_card_missing("job-card-link"))


def test_extract_record_raises_partial_record_error_when_field_present_but_empty():
    card = """
    <div class="job-card-container">
      <h3 class="job-card-title">   </h3>
      <span class="job-card-company">Acme Corp</span>
      <span class="job-card-location">Istanbul, Turkey</span>
      <time class="job-card-date">3 days ago</time>
      <p class="job-card-description">Some description.</p>
      <a class="job-card-link" href="https://www.linkedin.com/jobs/view/12345">View</a>
    </div>
    """
    with pytest.raises(PartialRecordError, match="title"):
        extract_record(card)


def test_extract_records_skips_broken_card_and_processes_others():
    broken_card = _card_missing("job-card-title")
    raw_cards = [WELL_FORMED_CARD, broken_card, WELL_FORMED_CARD]

    records = extract_records(raw_cards)

    # Roadmap M3.4 "Beklenen Sonuc": bozuk kart atlanir, akis DEVAM EDER -
    # diger IKI gecerli kart islenmis olmalidir.
    assert len(records) == 2
    assert all(record.title == "Sales Executive" for record in records)


def test_extract_records_logs_a_warning_when_a_card_is_skipped(caplog):
    broken_card = _card_missing("job-card-title")

    with caplog.at_level(logging.WARNING):
        extract_records([broken_card])

    assert any("title" in message for message in caplog.messages)


def test_extract_records_returns_empty_list_for_empty_input():
    assert extract_records([]) == []


def test_extract_records_preserves_order_of_successfully_extracted_records():
    first_card = WELL_FORMED_CARD.replace("Sales Executive", "First Job")
    second_card = WELL_FORMED_CARD.replace("Sales Executive", "Second Job")
    broken_card = _card_missing("job-card-title")

    records = extract_records([first_card, broken_card, second_card])

    assert [record.title for record in records] == ["First Job", "Second Job"]


def test_extract_record_wraps_unexpected_parsing_errors_as_partial_record_error(monkeypatch):
    # Bagimsiz incelemede bulunan Major bulgu: TDD Section 20, PartialRecordError'i
    # genis bir sekilde "Tek bir ilan kaydinin ayristirilamamasi" olarak
    # tanimlar - yalnizca "eksik/bos zorunlu alan" ile sinirli degildir.
    # BeautifulSoup'un/secici degerlendirmesinin KENDISININ beklenmedik bir
    # hata firlatmasi da (orn. pathological nested HTML) bir kaydin
    # ayristirilamamasi sayilmalidir.
    def _boom(*args, **kwargs):
        raise RecursionError("simulated pathological HTML")

    monkeypatch.setattr(module_under_test, "BeautifulSoup", _boom)

    with pytest.raises(PartialRecordError):
        extract_record(WELL_FORMED_CARD)


def test_extract_records_continues_past_an_unexpected_parsing_error(monkeypatch):
    # Roadmap M3.4'un kendi adinin ikinci yarisi ("...ve Kismi Hata
    # Toleransi"): TEK bir kartin ayristirilmasindaki BEKLENMEDIK bir hata
    # (yalnizca bilinen "alan eksik/bos" durumu degil), diger kartlarin
    # islenmesini durdurmamalidir.
    real_beautifulsoup = module_under_test.BeautifulSoup

    def _flaky_beautifulsoup(raw_html, parser):
        if raw_html == "PATHOLOGICAL":
            raise RecursionError("simulated pathological HTML")
        return real_beautifulsoup(raw_html, parser)

    monkeypatch.setattr(module_under_test, "BeautifulSoup", _flaky_beautifulsoup)

    records = extract_records([WELL_FORMED_CARD, "PATHOLOGICAL", WELL_FORMED_CARD])

    assert len(records) == 2


# ---------------------------------------------------------------------------
# RateLimiter (Roadmap M3.5, TDD Section 22) - istekler arasi (Playwright'a
# HER cagirinin ONCESINDE, ilk istek HARIC) sabit bir gecikmeye simetrik bir
# zamanlama sapmasi (jitter) ekler. Proje talimatiyla acikca onaylanan
# tasarim: `delay_seconds`/`jitter_seconds`/`sleep`, `max_jobs_per_run`'un
# KENDI ONAYLANMIS deseniyle AYNI sekilde duz fonksiyon parametreleridir -
# config semasina (config/schema.py) HICBIR SEKILDE dokunulmaz.
# ---------------------------------------------------------------------------


def test_collect_raw_job_cards_does_not_delay_before_the_first_request():
    target_criteria = _target_criteria()
    port = _FakeLinkedInPort()  # tanimsiz sorgu -> ilk istek hemen bos doner
    sleep = _recording_sleep()

    collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=200,
        delay_seconds=3.0,
        jitter_seconds=1.0,
        linkedin_retry_attempts=3,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=5,
        sleep=sleep,
    )

    # Tek bir istek yapildi (bos donen) - "istekler ARASI" gecikmenin
    # uygulanacagi bir ikinci istek hic olmadi.
    assert sleep.calls == []


def test_collect_raw_job_cards_delays_between_subsequent_requests():
    target_criteria = _target_criteria(
        departments={
            "Sales & Business Development": ["Sales"],
            "Marketing": ["Marketing"],
        }
    )
    port = _FakeLinkedInPort()  # her iki sorgu da hemen bos doner
    sleep = _recording_sleep()

    collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=200,
        delay_seconds=3.0,
        jitter_seconds=1.0,
        linkedin_retry_attempts=3,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=5,
        sleep=sleep,
    )

    # 2 istek (2 departman sorgusu) -> aralarinda TAM OLARAK 1 gecikme.
    assert len(sleep.calls) == 1


def test_collect_raw_job_cards_delays_between_pages_of_the_same_query():
    target_criteria = _target_criteria()
    port = _FakeLinkedInPort(
        pages_by_query={
            ("Istanbul", '"Sales" OR "Sales Executive"'): [
                ["card-0"],
                ["card-1"],
                # sayfa 2 tanimsiz -> bos doner, sayfalama burada durur
            ],
        }
    )
    sleep = _recording_sleep()

    collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=200,
        delay_seconds=3.0,
        jitter_seconds=1.0,
        linkedin_retry_attempts=3,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=5,
        sleep=sleep,
    )

    # 3 istek yapildi (sayfa 0, 1, 2-bos) -> aralarinda 2 gecikme. Hiz
    # sinirlamasi yalnizca AYRI sorgular arasinda degil, AYNI sorgunun
    # sayfalari arasinda da uygulanmalidir - her ikisi de gercek birer
    # LinkedIn istegidir.
    assert len(sleep.calls) == 2


def test_collect_raw_job_cards_delay_is_within_configured_jitter_range():
    target_criteria = _target_criteria(
        departments={
            "Sales & Business Development": ["Sales"],
            "Marketing": ["Marketing"],
            "Consulting": ["Consulting"],
        }
    )
    port = _FakeLinkedInPort()
    sleep = _recording_sleep()

    collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=200,
        delay_seconds=3.0,
        jitter_seconds=1.0,
        linkedin_retry_attempts=3,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=5,
        sleep=sleep,
    )

    # 3 istek -> 2 gecikme; her biri [3-1, 3+1] = [2, 4] araliginda olmali.
    assert len(sleep.calls) == 2
    assert all(2.0 <= duration <= 4.0 for duration in sleep.calls)


def test_collect_raw_job_cards_delay_never_negative_when_jitter_exceeds_delay():
    target_criteria = _target_criteria(
        departments={
            "Sales & Business Development": ["Sales"],
            "Marketing": ["Marketing"],
        }
    )
    port = _FakeLinkedInPort()
    sleep = _recording_sleep()

    collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=200,
        delay_seconds=0.5,
        jitter_seconds=5.0,
        linkedin_retry_attempts=3,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=5,
        sleep=sleep,
    )

    # Jitter, gecikmeden buyuk olsa bile, negatif bir bekleme suresi asla
    # `sleep()`'e gecilmemelidir.
    assert len(sleep.calls) == 1
    assert all(duration >= 0.0 for duration in sleep.calls)


def test_collect_raw_job_cards_default_sleep_measures_real_elapsed_time():
    # Roadmap M3.5 "Tamamlanma Dogrulamasi"nin dogrudan karsiligi: "Test
    # calistirmasinda istekler arasi gecen sure olculur ve konfigure
    # edilen aralikla uyumlu oldugu dogrulanir." Gercek `time.sleep`
    # (varsayilan `sleep` parametresi) kullanilir; test suitini
    # yavaslatmamak icin cok kucuk (milisaniye mertebesinde) degerler
    # secilir.
    target_criteria = _target_criteria(
        departments={
            "Sales & Business Development": ["Sales"],
            "Marketing": ["Marketing"],
        }
    )
    port = _FakeLinkedInPort()

    start = time.monotonic()
    collect_raw_job_cards(
        port,
        ACCOUNT_ID,
        target_criteria,
        max_jobs_per_run=200,
        delay_seconds=0.05,
        jitter_seconds=0.01,
        linkedin_retry_attempts=3,
        retry_base_delay_ms=0,
        retry_max_delay_ms=0,
        linkedin_consecutive_failure_threshold=5,
    )
    elapsed = time.monotonic() - start

    # 2 istek -> 1 gecikme, [0.04, 0.06] araliginda olmali; yavas CI
    # makineleri icin comert bir ust sinir birakilir.
    assert 0.03 <= elapsed <= 0.5
