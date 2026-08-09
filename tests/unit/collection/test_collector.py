"""collection/collector.py icin birim testleri (Roadmap M3.3, FR-21).

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
"""

from __future__ import annotations

import logging
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


class _FakeLinkedInPort(LinkedInPort):
    """Sahte `LinkedInPort`: `search_jobs_page` cagrilarini kaydeder ve
    `pages_by_query`'de tanimlanan (location, keywords) -> sayfa listesi
    eslemesine gore ham kart listeleri doner. Tanimlanmamis bir sorgu veya
    `len(pages)` disindaki bir sayfa istegi bos liste (dogal sayfalama
    sonu) doner.
    """

    def __init__(self, pages_by_query: dict[tuple[str, str], list[list[str]]] | None = None):
        self._pages_by_query = pages_by_query or {}
        self.calls: list[tuple[UUID, str, str, int]] = []

    def ensure_session(self, account_id: UUID) -> None:
        raise NotImplementedError("M3.3 testlerinde kullanilmaz")

    def validate(self, account_id: UUID) -> None:
        raise NotImplementedError("M3.3 testlerinde kullanilmaz")

    def search_jobs_page(
        self, account_id: UUID, location: str, keywords: str, page: int
    ) -> list[str]:
        self.calls.append((account_id, location, keywords, page))
        pages = self._pages_by_query.get((location, keywords))
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

    collect_raw_job_cards(port, ACCOUNT_ID, target_criteria, max_jobs_per_run=200)

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

    collect_raw_job_cards(port, ACCOUNT_ID, target_criteria, max_jobs_per_run=200)

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

    raw_cards, collection_capped = collect_raw_job_cards(
        port, ACCOUNT_ID, target_criteria, max_jobs_per_run=200
    )

    assert raw_cards == ["card-0-a", "card-0-b", "card-1-a"]
    assert collection_capped is False
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

    raw_cards, collection_capped = collect_raw_job_cards(
        port, ACCOUNT_ID, target_criteria, max_jobs_per_run=3
    )

    # Roadmap M3.3 "Tamamlanma Dogrulamasi": "tam olarak <=5 sonuc" -
    # sinira ulasildiginda sayfanin geri kalani dahil edilmemelidir.
    assert raw_cards == ["card-1", "card-2", "card-3"]
    assert collection_capped is True


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

    raw_cards, collection_capped = collect_raw_job_cards(
        port, ACCOUNT_ID, target_criteria, max_jobs_per_run=2
    )

    assert raw_cards == ["card-1", "card-2"]
    assert collection_capped is True
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

    raw_cards, collection_capped = collect_raw_job_cards(
        port, ACCOUNT_ID, target_criteria, max_jobs_per_run=200
    )

    assert raw_cards == ["card-1", "card-2"]
    assert collection_capped is False


def test_collect_raw_job_cards_passes_account_id_through():
    target_criteria = _target_criteria()
    port = _FakeLinkedInPort()

    collect_raw_job_cards(port, ACCOUNT_ID, target_criteria, max_jobs_per_run=200)

    assert all(acc == ACCOUNT_ID for acc, _loc, _kw, _page in port.calls)


def test_collect_raw_job_cards_propagates_session_invalid_error():
    class _RaisingPort(_FakeLinkedInPort):
        def search_jobs_page(self, account_id, location, keywords, page):
            raise SessionInvalidError("oturum gecersiz")

    target_criteria = _target_criteria()

    with pytest.raises(SessionInvalidError):
        collect_raw_job_cards(_RaisingPort(), ACCOUNT_ID, target_criteria, max_jobs_per_run=200)


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

    raw_cards, collection_capped = collect_raw_job_cards(
        port, ACCOUNT_ID, target_criteria, max_jobs_per_run=0
    )

    assert raw_cards == []
    assert collection_capped is True
    assert port.calls == []


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
