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

from uuid import UUID, uuid4

import pytest

from linkedinbot.collection.collector import collect_raw_job_cards
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
