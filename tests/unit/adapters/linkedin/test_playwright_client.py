"""playwright_client.py icin birim testleri (Roadmap M3.1; Faz 13:
storage_state snapshot -> persistent Chromium profili mimari gecisi).

Gercek bir tarayici/LinkedIn'e HICBIR ZAMAN dokunulmaz - `sync_playwright`
tamamen sahtelenir (monkeypatch). Bu, hem CI'da calisabilmesini hem de
"kullanicinin kendi kimlik bilgilerini dogrudan tarayiciya girdigi"
tasarim kararinin (proje talimatiyla onaylandi) test edilebilir tek yolu
olmasini saglar - gercek bir insan mudahalesi gerektiren akisi otomatik
test etmenin baska bir yolu yoktur.

**Faz 13 mimari degisikligi (bu dosyanin kendisi icin onemli):** ONCEKI
sahte altyapi `chromium.launch()` + `browser.new_context(storage_state=...)`
ikilisini modelliyordu (`_FakeBrowser` + `_FakeContext` ayri nesnelerdi).
Yeni mimaride HER UC fonksiyon `chromium.launch_persistent_context(
user_data_dir, ...)` kullanir - bu, gercek Playwright'ta da AYRI bir
Browser nesnesi DONDURMEZ, dogrudan bir `BrowserContext`tir. Bu yuzden
`_FakeBrowser` sinifi KALDIRILDI; `_FakeContext` artik KENDI `close()`/
`closed` durumunu tasir (`browser.closed` -> `context.closed`). `dict`
(storage_state) parametreleri, disposable, GERCEK-OLMAYAN `tmp_path`
tabanli `Path` (profil dizini) parametreleriyle degistirildi.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from linkedinbot.adapters.linkedin import playwright_client as module_under_test
from linkedinbot.adapters.linkedin.playwright_client import (
    LOGIN_URL,
    SEARCH_URL,
    SESSION_CHECK_URL,
    JobCardsResponseTimeoutError,
    LoginTimeoutError,
    _build_synthetic_card_html,
    _format_listed_date,
    _job_id_from_jobposting_urn,
    _parse_job_cards_response,
    _parse_job_descriptions_response,
    check_session_is_valid,
    fetch_search_results_page,
    perform_interactive_login,
)

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def profile_dir(tmp_path: Path) -> Path:
    """Disposable, GERCEK-OLMAYAN bir hesap-bazli profil dizini yolu -
    testler arasi hicbir gercek LinkedIn profiline (`browser-profile/`)
    dokunulmaz/okunmaz (bkz. proje talimatinin "testlerde gercek profile
    kullanma" kurali)."""
    return tmp_path / "profile"


class _FakeGotoResponse:
    """Gercek Playwright `Page.goto()`'nun dondurdugu `Response` nesnesinin
    minimal bir sahtesi - yalnizca `check_session_is_valid()`'in okudugu
    `.status` alanini tasir (M12'nin canli dogrulamasi sirasinda eklenen
    teshis loglamasi icin)."""

    def __init__(self, status: int | None):
        self.status = status


class _FakePage:
    """M10.2 mimari evrimi: `fetch_search_results_page()` artik DOM
    sorgulamaz - Playwright'in KENDI ag yaniti olaylarini (`page.on(
    "response", ...)`) dinler. Bu sahte, `response_events` listesindeki
    (url, body) ciftlerini, `wait_for_timeout()` her cagrildiginda (gercek
    Playwright'in arka plan thread'inin ag olaylarini ISLEMEYE DEVAM ETMESI
    davranisini taklit ederek - bkz. `_wait_until()`'in kendi dokumani)
    kademeli olarak "teslim eder" - boylece hem ANINDA hem GECIKMELI yanit
    senaryolari (ve HIC gelmeyen bir yanitin zaman asimina ugramasi)
    gercekci sekilde test edilebilir.
    """

    def __init__(
        self,
        raise_on_wait: Exception | None = None,
        landing_url: str | None = None,
        raise_on_goto: Exception | None = None,
        response_events: list[tuple[str, str]] | None = None,
        response_event_delay_polls: int = 0,
        goto_status: int | None = 200,
    ):
        self.goto_calls: list[str] = []
        self.wait_for_url_calls: list[tuple[str, int]] = []
        self.wait_for_timeout_calls: list[int] = []
        self._raise_on_wait = raise_on_wait
        self._landing_url = landing_url
        self._raise_on_goto = raise_on_goto
        self._response_events = list(response_events or [])
        self._response_event_delay_polls = response_event_delay_polls
        self._response_handler = None
        self._poll_count = 0
        self._goto_status = goto_status
        self.url = ""

    def goto(self, url: str) -> _FakeGotoResponse:
        self.goto_calls.append(url)
        # Gercek Playwright'te ag yanitlari `goto()`'nun kendi "load"
        # beklemesiyle ES ZAMANLI/ONCE gelebilir (canli olarak dogrulandi -
        # M10.2 duzeltmesi) - bu yuzden `response_events` (ANINDA teslimat
        # modunda) `raise_on_goto` kontrolunden ONCE teslim edilir. Mevcut
        # butun testler `raise_on_goto`'yu bos `response_events` ile
        # kullandigi icin bu sira degisikligi onlar icin bir no-op'tur.
        if self._response_event_delay_polls == 0:
            self._deliver_response_events()
        if self._raise_on_goto is not None:
            raise self._raise_on_goto
        self.url = self._landing_url if self._landing_url is not None else url
        return _FakeGotoResponse(self._goto_status)

    def wait_for_url(self, pattern: str, timeout: int) -> None:
        self.wait_for_url_calls.append((pattern, timeout))
        if self._raise_on_wait is not None:
            raise self._raise_on_wait

    def wait_for_timeout(self, ms: int) -> None:
        self.wait_for_timeout_calls.append(ms)
        self._poll_count += 1
        if self._poll_count == self._response_event_delay_polls:
            self._deliver_response_events()

    def on(self, event: str, handler) -> None:
        if event == "response":
            self._response_handler = handler

    def _deliver_response_events(self) -> None:
        if self._response_handler is None:
            return
        for url, body in self._response_events:
            self._response_handler(_FakeResponse(url, body))


class _FakeResponse:
    def __init__(self, url: str, body: str):
        self.url = url
        self._body = body

    def text(self) -> str:
        return self._body


class _FakeContext:
    """`launch_persistent_context()`'in dondurdugu TEK nesnenin sahtesi -
    ONCEKI mimarideki ayri `_FakeBrowser`+`_FakeContext` ikilisinin YERINI
    alir (gercek Playwright'ta da `launch_persistent_context()` ayri bir
    Browser nesnesi DONDURMEZ, dogrudan bir BrowserContext'tir - bu yuzden
    kapanma durumu (`closed`) artik BU sinifin kendi sorumlulugudur)."""

    def __init__(self, page: _FakePage):
        self._page = page
        self.closed = False

    def new_page(self) -> _FakePage:
        return self._page

    def close(self) -> None:
        self.closed = True


class _FakeChromium:
    def __init__(self, context: _FakeContext):
        self._context = context
        self.launch_persistent_context_calls: list[tuple[str, dict]] = []

    def launch_persistent_context(self, user_data_dir: str, **kwargs) -> _FakeContext:
        self.launch_persistent_context_calls.append((user_data_dir, kwargs))
        return self._context


class _FakePlaywright:
    def __init__(self, chromium: _FakeChromium):
        self.chromium = chromium


def _install_fake_playwright(
    monkeypatch,
    *,
    raise_on_wait: Exception | None = None,
    landing_url: str | None = None,
    raise_on_goto: Exception | None = None,
    response_events: list[tuple[str, str]] | None = None,
    response_event_delay_polls: int = 0,
    goto_status: int | None = 200,
):
    page = _FakePage(
        raise_on_wait=raise_on_wait,
        landing_url=landing_url,
        raise_on_goto=raise_on_goto,
        response_events=response_events,
        response_event_delay_polls=response_event_delay_polls,
        goto_status=goto_status,
    )
    context = _FakeContext(page)
    chromium = _FakeChromium(context)
    playwright_obj = _FakePlaywright(chromium)

    @contextmanager
    def _fake_sync_playwright():
        yield playwright_obj

    monkeypatch.setattr(module_under_test, "sync_playwright", _fake_sync_playwright)
    return page, context, chromium


def test_perform_interactive_login_launches_headed_browser(monkeypatch, profile_dir):
    # "headless=False" kritik - kullanicinin GORUP kendi kimlik bilgilerini
    # girebilecegi bir pencere olmadan interaktif giris imkansizdir.
    _page, _context, chromium = _install_fake_playwright(monkeypatch)

    perform_interactive_login(profile_dir)

    user_data_dir, kwargs = chromium.launch_persistent_context_calls[0]
    assert user_data_dir == str(profile_dir)
    assert kwargs == {"headless": False}


def test_perform_interactive_login_navigates_to_linkedin_login_page(monkeypatch, profile_dir):
    page, _context, _chromium = _install_fake_playwright(monkeypatch)

    perform_interactive_login(profile_dir)

    assert page.goto_calls == [LOGIN_URL]


def test_perform_interactive_login_waits_for_authenticated_redirect(monkeypatch, profile_dir):
    page, _context, _chromium = _install_fake_playwright(monkeypatch)

    perform_interactive_login(profile_dir)

    assert len(page.wait_for_url_calls) == 1
    pattern, timeout = page.wait_for_url_calls[0]
    assert "feed" in pattern
    assert timeout > 0


def test_perform_interactive_login_creates_profile_directory_with_restricted_permissions(
    monkeypatch, tmp_path
):
    # Faz 13: kalici profil dizini (henuz yoksa) burada olusturulur, 0700
    # izniyle - authentication state tasiyacagi icin (secrets/ dizini icin
    # TDD Section 24'un ZATEN uyguladigi ayni disiplin).
    _install_fake_playwright(monkeypatch)
    account_profile_dir = tmp_path / "browser-profile" / "some-account-id"

    perform_interactive_login(account_profile_dir)

    assert account_profile_dir.exists()
    assert account_profile_dir.stat().st_mode & 0o777 == 0o700


def test_perform_interactive_login_closes_context_after_success(monkeypatch, profile_dir):
    _page, context, _chromium = _install_fake_playwright(monkeypatch)

    perform_interactive_login(profile_dir)

    assert context.closed is True


def test_perform_interactive_login_raises_login_timeout_error_on_timeout(monkeypatch, profile_dir):
    _page, _context, _chromium = _install_fake_playwright(
        monkeypatch, raise_on_wait=PlaywrightTimeoutError("Timeout 300000ms exceeded")
    )

    with pytest.raises(LoginTimeoutError):
        perform_interactive_login(profile_dir)


def test_perform_interactive_login_closes_context_even_on_timeout(monkeypatch, profile_dir):
    # Ic-denetim odakli test: tarayici penceresi acik birakilirsa (orn.
    # kullanici 2FA'yi tamamlamazsa) surec sonsuza kadar asili kalan bir
    # tarayici surecine neden olabilir - try/finally bunu onlemeli.
    _page, context, _chromium = _install_fake_playwright(
        monkeypatch, raise_on_wait=PlaywrightTimeoutError("Timeout 300000ms exceeded")
    )

    with pytest.raises(LoginTimeoutError):
        perform_interactive_login(profile_dir)

    assert context.closed is True


def test_perform_interactive_login_timeout_message_is_actionable(monkeypatch, profile_dir):
    # Ham Playwright TimeoutError'i ("Timeout 300000ms exceeded") "ne
    # bekleniyordu" baglami tasimaz - kullaniciya giris/2FA'nin
    # tamamlanmadigini acikca soyleyen bir mesaj gerekir.
    _page, _context, _chromium = _install_fake_playwright(
        monkeypatch, raise_on_wait=PlaywrightTimeoutError("Timeout 300000ms exceeded")
    )

    with pytest.raises(LoginTimeoutError, match="giris"):
        perform_interactive_login(profile_dir)


# ---------------------------------------------------------------------------
# check_session_is_valid (Roadmap M3.2) - kayitli bir kalici Chromium
# profilinin HALA gecerli olup olmadigini, insan mudahalesi olmadan
# (headless), canli olarak kontrol eder. M3.1'in interaktif giris akisindan
# farkli olarak burada beklenen bir "insan tamamlar" adimi yoktur - ya
# oturum kabul edilir ya da edilmez, sonuc `goto()` tamamlaninca zaten
# bellidir.
# ---------------------------------------------------------------------------


def test_check_session_is_valid_launches_headless_browser(monkeypatch, profile_dir):
    # M3.1'in aksine burada hicbir insan mudahalesi beklenmez - gorunur bir
    # pencereye gerek yoktur.
    _page, _context, chromium = _install_fake_playwright(monkeypatch, landing_url=SESSION_CHECK_URL)

    check_session_is_valid(profile_dir)

    user_data_dir, kwargs = chromium.launch_persistent_context_calls[0]
    assert user_data_dir == str(profile_dir)
    assert kwargs == {"headless": True}


def test_check_session_is_valid_navigates_to_session_check_url(monkeypatch, profile_dir):
    page, _context, _chromium = _install_fake_playwright(monkeypatch, landing_url=SESSION_CHECK_URL)

    check_session_is_valid(profile_dir)

    assert page.goto_calls == [SESSION_CHECK_URL]


def test_check_session_is_valid_returns_true_when_still_on_authenticated_page(
    monkeypatch, profile_dir
):
    _install_fake_playwright(monkeypatch, landing_url=SESSION_CHECK_URL)

    assert check_session_is_valid(profile_dir) is True


def test_check_session_is_valid_returns_false_when_redirected_to_login(monkeypatch, profile_dir):
    # Sunucu tarafinda gecersiz/suresi dolmus bir oturum, LinkedIn'i
    # dogrudan giris sayfasina yonlendirmeye zorlar - bu, "invalidate the
    # session by deleting a cookie" (Roadmap M3.2 Tamamlanma Dogrulamasi)
    # senaryosunun canli davranis karsiligidir.
    _install_fake_playwright(monkeypatch, landing_url="https://www.linkedin.com/login")

    assert check_session_is_valid(profile_dir) is False


def test_check_session_is_valid_closes_context_after_check(monkeypatch, profile_dir):
    _page, context, _chromium = _install_fake_playwright(monkeypatch, landing_url=SESSION_CHECK_URL)

    check_session_is_valid(profile_dir)

    assert context.closed is True


def test_check_session_is_valid_closes_context_even_if_navigation_fails(monkeypatch, profile_dir):
    _page, context, _chromium = _install_fake_playwright(
        monkeypatch, raise_on_goto=RuntimeError("simulated network failure")
    )

    with pytest.raises(RuntimeError, match="simulated network failure"):
        check_session_is_valid(profile_dir)

    assert context.closed is True


def test_check_session_is_valid_does_not_reclassify_navigation_errors(monkeypatch, profile_dir):
    # Onemli ayrim (TDD Section 20: TransientError vs PermanentError): bir
    # ag/navigasyon hatasi "oturum gecersiz" DEGILDIR. check_session_is_valid()
    # bu hatayi SESSIZCE False'a cevirmemeli/yutmamalidir - ham hata oldugu
    # gibi yukari sizmalidir (siniflandirma cagiranin/gelecekteki M9.3'un
    # isidir).
    _install_fake_playwright(monkeypatch, raise_on_goto=RuntimeError("simulated network failure"))

    with pytest.raises(RuntimeError, match="simulated network failure"):
        check_session_is_valid(profile_dir)


def test_check_session_is_valid_logs_no_warning_when_session_is_valid(
    monkeypatch, caplog, profile_dir
):
    # M12'nin canli dogrulamasi sirasinda bulunan bir gozlemlenebilirlik
    # boslugunun kapatilmasi: teshis loglamasi YALNIZCA basarisiz (gecersiz)
    # durumda tetiklenmeli - basarili yolun davranisi/log ciktisi degismemeli.
    _install_fake_playwright(monkeypatch, landing_url=SESSION_CHECK_URL)

    with caplog.at_level("WARNING", logger=module_under_test.__name__):
        result = check_session_is_valid(profile_dir)

    assert result is True
    assert caplog.records == []


def test_check_session_is_valid_logs_sanitized_redirect_url_and_status_on_failure(
    monkeypatch, caplog, profile_dir
):
    _install_fake_playwright(
        monkeypatch,
        landing_url="https://www.linkedin.com/checkpoint/challenge?token=super-secret-value",
        goto_status=302,
    )

    with caplog.at_level("WARNING", logger=module_under_test.__name__):
        result = check_session_is_valid(profile_dir)

    assert result is False
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    # Yol (teshis icin gerekli bilgi) loglanir...
    assert "https://www.linkedin.com/checkpoint/challenge" in message
    assert "302" in message
    assert "session_valid=False" in message
    # ...ama sorgu dizesi (hassas token TASIYABILECEGI icin) ASLA loglanmaz.
    assert "token" not in message
    assert "super-secret-value" not in message


def test_check_session_is_valid_never_logs_the_profile_directory_path(
    monkeypatch, caplog, tmp_path
):
    # Cerez/profil DEGERLERI hicbir kosulda loglanmamalidir - yalnizca
    # gidilen sayfanin (sanitize edilmis) yolu ve HTTP durumu loglanir. Faz
    # 13'te bu endise yapisal olarak daha da guclendi:
    # check_session_is_valid() artik cerez DEGERLERINI (bir dict olarak)
    # hic almiyor - yalnizca bir dizin YOLU aliyor; bu test o yolun KENDISI
    # de loglanmadigini dogrular.
    secret_profile_dir = tmp_path / "super-secret-profile-name"
    _install_fake_playwright(
        monkeypatch, landing_url="https://www.linkedin.com/login", goto_status=200
    )

    with caplog.at_level("WARNING", logger=module_under_test.__name__):
        check_session_is_valid(secret_profile_dir)

    assert str(secret_profile_dir) not in caplog.text


def test_check_session_is_valid_logs_null_status_when_goto_returns_none(
    monkeypatch, caplog, profile_dir
):
    # `page.goto()`'nun dondurdugu yanitin `.status`'u bilinmiyorsa (orn.
    # `None`), teshis loglamasi bunu bir hataya (AttributeError/format hatasi)
    # DONUSTURMEDEN, sadece "durum bilinmiyor" olarak loglamalidir.
    _install_fake_playwright(
        monkeypatch, landing_url="https://www.linkedin.com/login", goto_status=None
    )

    with caplog.at_level("WARNING", logger=module_under_test.__name__):
        result = check_session_is_valid(profile_dir)

    assert result is False
    assert len(caplog.records) == 1
    assert "None" in caplog.records[0].getMessage()


# ---------------------------------------------------------------------------
# fetch_search_results_page (Roadmap M3.3; M10.2 mimari evrimi) - kalici bir
# Chromium profilini yukleyip, verilen (location, keywords) sorgusu icin
# belirtilen sayfadaki ilanlari, LinkedIn'in KENDI (belgesiz) API'sinin ag
# yaniti govdelerinden (DOM'dan DEGIL - bkz. playwright_client.py'nin modul
# dokumaninin "M10.2 mimari evrimi" notu) BIZIM tanimladigimiz sentetik bir
# HTML olarak doner. Sayfalama (hangi sayfaya kadar devam edilecegi, FR-21
# sinirinin nerede uygulanacagi) burada YOKTUR - bu, collection/collector.py'nin
# (PaginationController) sorumlulugudur; bu fonksiyon yalnizca TEK bir
# sayfayi getirir.
# ---------------------------------------------------------------------------

_CARDS_RESPONSE_URL = (
    "https://www.linkedin.com/voyager/api/voyagerJobsDashJobCards"
    "?decorationId=com.linkedin.voyager.dash.deco.jobs.search.JobSearchCardsCollection-220"
    "&count=25&q=jobSearch"
)
# M10.2 duzeltmesi (canli olarak dogrulanan bir bulgu): LinkedIn'in aciklama
# metnini tasiyan GraphQL yanitinin `queryId`'si `voyagerJobsDashJobCards.<hash>`
# ile BASLAR - yani bu URL, `_JOB_CARDS_RESPONSE_URL_MARKER`'in ESKI (capasiz)
# haliyle YANLISLIKLA eslesiyordu. Bu sabit KASITLI OLARAK bu GERCEK, ikircikli
# sekli kullanir - asagidaki TUM `fetch_search_results_page` testleri boylece
# regresyonu dogal olarak kapsar (bkz. ayrica, bunu ACIKCA belgeleyen
# `test_fetch_search_results_page_captures_description_when_its_url_also_matches_cards_marker`
# adli test).
_DESCRIPTIONS_RESPONSE_URL = (
    "https://www.linkedin.com/voyager/api/graphql"
    "?includeWebMetadata=true&variables=(jobPostingDetailDescription_start:0)"
    "&queryId=voyagerJobsDashJobCards.9c135b2568ee44623733b4a578d25279"
)


def _cards_response_body(*cards: dict) -> str:
    """`elements`/`included` ciftini, `_parse_job_cards_response()`'in
    bekledigi minimal gercekci sekilde uretir - `cards` her biri {"job_id",
    "title", "company", "location", "time_at" (opsiyonel)} tasiyan dict'ler."""
    import json

    elements = [
        {
            "jobCardUnion": {
                "*jobPostingCard": f"urn:li:fsd_jobPostingCard:({c['job_id']},JOBS_SEARCH)"
            }
        }
        for c in cards
    ]
    included = []
    for c in cards:
        footer_items = []
        if c.get("time_at") is not None:
            footer_items.append({"type": "LISTED_DATE", "timeAt": c["time_at"]})
        included.append(
            {
                "$type": "com.linkedin.voyager.dash.jobs.JobPostingCard",
                "entityUrn": f"urn:li:fsd_jobPostingCard:({c['job_id']},JOBS_SEARCH)",
                "jobPostingUrn": f"urn:li:fsd_jobPosting:{c['job_id']}",
                "jobPostingTitle": c["title"],
                "primaryDescription": {"text": c["company"]},
                "secondaryDescription": {"text": c["location"]},
                "footerItems": footer_items,
            }
        )
    return json.dumps({"data": {"elements": elements}, "included": included})


def _descriptions_response_body(descriptions_by_job_id: dict[str, str]) -> str:
    import json

    included = [
        {
            "$type": "com.linkedin.voyager.dash.jobs.JobDescription",
            "*jobPosting": f"urn:li:fsd_jobPosting:{job_id}",
            "descriptionText": {"text": text},
        }
        for job_id, text in descriptions_by_job_id.items()
    ]
    return json.dumps({"included": included})


def test_fetch_search_results_page_launches_headless_browser(monkeypatch, profile_dir):
    # Toplama otomatik/gozetimsiz calisir (ASM-8) - M3.1'in interaktif
    # girisinin aksine burada insan mudahalesi beklenmez.
    _page, _context, chromium = _install_fake_playwright(
        monkeypatch, response_events=[(_CARDS_RESPONSE_URL, _cards_response_body())]
    )

    fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0)

    user_data_dir, kwargs = chromium.launch_persistent_context_calls[0]
    assert user_data_dir == str(profile_dir)
    assert kwargs == {"headless": True}


def test_fetch_search_results_page_navigates_to_search_url_with_query_params(
    monkeypatch, profile_dir
):
    page, _context, _chromium = _install_fake_playwright(
        monkeypatch, response_events=[(_CARDS_RESPONSE_URL, _cards_response_body())]
    )

    fetch_search_results_page(profile_dir, "Istanbul", '"Sales" OR "Key Account"', 2)

    assert len(page.goto_calls) == 1
    url = page.goto_calls[0]
    assert url.startswith(SEARCH_URL)
    assert "location=Istanbul" in url
    assert "keywords=%22Sales%22+OR+%22Key+Account%22" in url
    # 2. sayfa (0-indexed), varsayilan sayfa boyutunun 2 katinda baslamali.
    assert "start=50" in url


def test_fetch_search_results_page_first_page_starts_at_zero(monkeypatch, profile_dir):
    page, _context, _chromium = _install_fake_playwright(
        monkeypatch, response_events=[(_CARDS_RESPONSE_URL, _cards_response_body())]
    )

    fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0)

    assert "start=0" in page.goto_calls[0]


def test_fetch_search_results_page_raises_when_no_cards_response_arrives(monkeypatch, profile_dir):
    # M11.1 (Roadmap Faz 11): yanit hic gelmemesi (zaman asimi) artik
    # sayfalamanin dogal sonuyla (bos liste) KARISTIRILMAZ - bu bir
    # aktarim/erisim sorunudur ve collector.py'nin retry/devre-kesici
    # mekanizmasina akmasi icin bir istisna olarak firlatilmalidir (bkz.
    # asagidaki "cards_response_has_zero_elements" testi - GERCEKTEN
    # gelen ama sifir kart iceren bir yanit hala `[]` doner).
    monkeypatch.setattr(module_under_test, "_JOB_CARDS_RESPONSE_TIMEOUT_MS", 50)
    _page, context, _chromium = _install_fake_playwright(monkeypatch, response_events=[])

    with pytest.raises(JobCardsResponseTimeoutError):
        fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0)

    # Diger her istisna-firlatma yolu icin zaten dogrulanan AYNI paylasilan
    # finally: context.close() garantisi - bkz.
    # test_fetch_search_results_page_closes_context_even_if_navigation_fails.
    assert context.closed is True


def test_fetch_search_results_page_returns_empty_list_when_cards_response_has_zero_elements(
    monkeypatch, profile_dir
):
    _install_fake_playwright(
        monkeypatch, response_events=[(_CARDS_RESPONSE_URL, _cards_response_body())]
    )

    assert fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0) == []


def test_fetch_search_results_page_closes_context_after_fetch(monkeypatch, profile_dir):
    _page, context, _chromium = _install_fake_playwright(
        monkeypatch, response_events=[(_CARDS_RESPONSE_URL, _cards_response_body())]
    )

    fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0)

    assert context.closed is True


def test_fetch_search_results_page_closes_context_even_if_navigation_fails(
    monkeypatch, profile_dir
):
    _page, context, _chromium = _install_fake_playwright(
        monkeypatch, raise_on_goto=RuntimeError("simulated network failure")
    )

    with pytest.raises(RuntimeError, match="simulated network failure"):
        fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0)

    assert context.closed is True


def test_fetch_search_results_page_keeps_cards_when_goto_times_out_after_capture(
    monkeypatch, profile_dir
):
    # Regresyon testi (M10.2 duzeltmesi): canli bir Bootstrap calistirmasinda
    # kanitlanan gercek bir kusur. Kart yaniti basariyla geldi/yakalandi
    # (t=7.7s), ama `goto()`'nun KENDI ic "load" beklemesi 30s'de zaman
    # asimina ugrayip, ZATEN yakalanmis olan veriyi fonksiyonun tamami iptal
    # edilerek SESSIZCE cope atiyordu. Bu test, `goto()`'nun (ANINDA teslim
    # edilen bir kart yanitindan HEMEN SONRA) bir `PlaywrightTimeoutError`
    # firlattigi TAM bu sirayi yeniden uretir - duzeltilmis kod, veri ZATEN
    # yakalandigi icin bu zaman asimini YOK saymali ve kartlari normal
    # sekilde ayristirip donmelidir.
    cards_body = _cards_response_body(
        {
            "job_id": "555",
            "title": "Trade Marketing Specialist",
            "company": "Acme Corp",
            "location": "Istanbul, Turkey",
            "time_at": 1785694003000,
        }
    )
    _page, context, _chromium = _install_fake_playwright(
        monkeypatch,
        response_events=[(_CARDS_RESPONSE_URL, cards_body)],
        raise_on_goto=PlaywrightTimeoutError(
            'Page.goto: Timeout 30000ms exceeded.\n  - waiting until "load"'
        ),
    )

    (result,) = fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0)

    assert 'data-job-id="555"' in result
    assert 'data-field="title">Trade Marketing Specialist<' in result
    assert context.closed is True


def test_fetch_search_results_page_still_raises_when_goto_times_out_and_no_cards_were_captured(
    monkeypatch, profile_dir
):
    # Ayni kusurun DIGER yonu (Gereksinim 7: "genuine no response ever
    # arrived" durumu icin mevcut retry davranisi korunmali): eger kart
    # yaniti HIC gelmediyse, `goto()`'nun zaman asimi HALA fatal olmali ve
    # yukari (cagiran `_fetch_page_with_retry`'nin retry mekanizmasina)
    # sizmalidir - aksi halde gercek bir ag/erisim sorunu sessizce yutulup
    # bos bir sonuc olarak yanlis yorumlanirdi.
    _page, context, _chromium = _install_fake_playwright(
        monkeypatch,
        response_events=[],
        raise_on_goto=PlaywrightTimeoutError(
            'Page.goto: Timeout 30000ms exceeded.\n  - waiting until "load"'
        ),
    )

    with pytest.raises(PlaywrightTimeoutError):
        fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0)

    assert context.closed is True


def test_fetch_search_results_page_builds_synthetic_html_from_a_real_response(
    monkeypatch, profile_dir
):
    cards_body = _cards_response_body(
        {
            "job_id": "555",
            "title": "Sales Executive",
            "company": "Acme Corp",
            "location": "Istanbul, Turkey",
            "time_at": 1785694003000,
        }
    )
    descriptions_body = _descriptions_response_body({"555": "We are hiring a Sales Executive."})
    _page, _context, _chromium = _install_fake_playwright(
        monkeypatch,
        response_events=[
            (_CARDS_RESPONSE_URL, cards_body),
            (_DESCRIPTIONS_RESPONSE_URL, descriptions_body),
        ],
    )

    (result,) = fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0)

    assert 'data-job-id="555"' in result
    assert 'data-field="title">Sales Executive<' in result
    assert 'data-field="company">Acme Corp<' in result
    assert 'data-field="location">Istanbul, Turkey<' in result
    assert 'data-field="date">2026-08-02<' in result
    assert 'data-field="description">We are hiring a Sales Executive.<' in result
    assert 'href="https://www.linkedin.com/jobs/view/555/"' in result


def test_fetch_search_results_page_preserves_order_across_multiple_cards(monkeypatch, profile_dir):
    cards_body = _cards_response_body(
        *[
            {
                "job_id": str(i),
                "title": f"Title {i}",
                "company": "Company",
                "location": "Istanbul",
                "time_at": 1785694003000,
            }
            for i in range(3)
        ]
    )
    descriptions_body = _descriptions_response_body({str(i): f"desc {i}" for i in range(3)})
    _page, _context, _chromium = _install_fake_playwright(
        monkeypatch,
        response_events=[
            (_CARDS_RESPONSE_URL, cards_body),
            (_DESCRIPTIONS_RESPONSE_URL, descriptions_body),
        ],
    )

    result = fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0)

    assert [f'data-job-id="{i}"' in html for i, html in enumerate(result)] == [True, True, True]
    assert all(f"Title {i}" in result[i] for i in range(3))


def test_fetch_search_results_page_escapes_html_special_characters_in_fields(
    monkeypatch, profile_dir
):
    cards_body = _cards_response_body(
        {
            "job_id": "555",
            "title": 'Title <script>&"',
            "company": "Company",
            "location": "Istanbul",
            "time_at": 1785694003000,
        }
    )
    _install_fake_playwright(monkeypatch, response_events=[(_CARDS_RESPONSE_URL, cards_body)])

    (result,) = fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0)

    assert "<script>" not in result
    assert "Title &lt;script&gt;&amp;&quot;" in result


def test_fetch_search_results_page_description_is_empty_when_no_descriptions_response_arrives(
    monkeypatch, profile_dir
):
    # Bir ilanin aciklamasi bulunamazsa (orn. aciklama yaniti hic gelmedi)
    # bos dize kalir - `extract_record()`'in KENDI "alan bulunamadi" kontrolu
    # bunu ele alir, burada bir istisna FIRLATILMAZ.
    monkeypatch.setattr(module_under_test, "_JOB_DESCRIPTIONS_RESPONSE_TIMEOUT_MS", 50)
    cards_body = _cards_response_body(
        {
            "job_id": "555",
            "title": "Title",
            "company": "Company",
            "location": "Istanbul",
            "time_at": 1785694003000,
        }
    )
    _install_fake_playwright(monkeypatch, response_events=[(_CARDS_RESPONSE_URL, cards_body)])

    (result,) = fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0)

    assert 'data-field="description"></span>' in result


def test_fetch_search_results_page_date_is_empty_when_listed_date_footer_item_missing(
    monkeypatch, profile_dir
):
    cards_body = _cards_response_body(
        {
            "job_id": "555",
            "title": "Title",
            "company": "Company",
            "location": "Istanbul",
            "time_at": None,
        }
    )
    _install_fake_playwright(monkeypatch, response_events=[(_CARDS_RESPONSE_URL, cards_body)])

    (result,) = fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0)

    assert 'data-field="date"></span>' in result


def test_fetch_search_results_page_handles_a_response_delayed_by_several_polls(
    monkeypatch, profile_dir
):
    # Ag yanitlari ASENKRON gelir (bkz. modul dokumaninin "M10.2 mimari
    # evrimi" notu) - `goto()`'nun ANINDA degil, birkac `wait_for_timeout()`
    # dongusunden SONRA gelen bir yaniti dogru sekilde yakalamalidir.
    cards_body = _cards_response_body(
        {
            "job_id": "555",
            "title": "Title",
            "company": "Company",
            "location": "Istanbul",
            "time_at": 1785694003000,
        }
    )
    page, _context, _chromium = _install_fake_playwright(
        monkeypatch,
        response_events=[(_CARDS_RESPONSE_URL, cards_body)],
        response_event_delay_polls=3,
    )

    result = fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0)

    assert len(result) == 1
    assert len(page.wait_for_timeout_calls) >= 3


def test_fetch_search_results_page_captures_description_when_its_url_also_matches_cards_marker(
    monkeypatch, profile_dir
):
    # Regresyon testi (M10.2 duzeltmesi): canli bir hesaba karsi dogrulanan
    # gercek bir kusur. LinkedIn'in aciklama metnini tasiyan GraphQL
    # yanitinin URL'si (`_DESCRIPTIONS_RESPONSE_URL`, bkz. kendi yorumu), HAM
    # "voyagerJobsDashJobCards" alt-dizesini KENDI `queryId=voyagerJobsDashJobCards.<hash>`
    # parametresinde tasir - eski (capasiz) `_JOB_CARDS_RESPONSE_URL_MARKER`
    # kontroluyle YANLISLIKLA eslesiyordu. Eski `elif` sirasi + "kart listesi
    # zaten yakalandi" durumu (kart listesi yaniti ONCE gelir) nedeniyle bu
    # yanit SESSIZCE dusuruluyor, `descriptions_by_job_id` HER ZAMAN bos
    # kaliyordu (butun ilanlarin `description` alaninin bos gelmesine,
    # dolayisiyla TUM kartlarin `PartialRecordError` ile atlanmasina yol
    # aciyordu).
    #
    # Duzeltme IKI parcalidir: (1) `_JOB_CARDS_RESPONSE_URL_MARKER` artik
    # `/api/voyagerJobsDashJobCards?` - yani GERCEK REST.li yoluna capa'lidir,
    # GraphQL uc noktasinin URL'si (HER ZAMAN `/api/graphql?`) buna asla
    # uymaz; (2) iki kontrol artik bagimsiz `if`'lerdir (`elif` DEGIL). Bu
    # test HER IKI korumayi da dogrular: asagidaki iddialar, "gercek dunya"
    # senaryosunun (ham alt-dizenin hala mevcut olmasi) yeniden uretildigini,
    # ama YENI capa'nin onu artik yanlislikla eslemedigini kanitlar - sonra
    # asil davranis dogrulanir.
    cards_body = _cards_response_body(
        {
            "job_id": "555",
            "title": "Title",
            "company": "Company",
            "location": "Istanbul",
            "time_at": 1785694003000,
        }
    )
    descriptions_body = _descriptions_response_body({"555": "Real description text."})
    assert "voyagerJobsDashJobCards" in _DESCRIPTIONS_RESPONSE_URL, (
        "bu test yalnizca, aciklama URL'sinin ham kart-listesi alt-dizesini "
        "de icerdigi (gercek LinkedIn davranisini yansitan) senaryoda anlamlidir"
    )
    assert module_under_test._JOB_CARDS_RESPONSE_URL_MARKER not in _DESCRIPTIONS_RESPONSE_URL, (
        "duzeltilmis (capa'li) isaret, aciklama URL'siyle ARTIK eslesmemelidir"
    )
    _install_fake_playwright(
        monkeypatch,
        response_events=[
            (_CARDS_RESPONSE_URL, cards_body),
            (_DESCRIPTIONS_RESPONSE_URL, descriptions_body),
        ],
    )

    (result,) = fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0)

    assert 'data-field="description">Real description text.<' in result


def test_fetch_search_results_page_captures_description_when_it_arrives_before_any_cards_response(
    monkeypatch, profile_dir
):
    # Ayni kusurun DIGER yonu: eger aciklama yaniti (her iki isaretle de
    # eslesen URL'siyle) kart-listesi yanitindan ONCE gelseydi, eski
    # `elif`+capasiz-isaret kombinasyonu onu YANLISLIKLA `captured_cards_body`'ye
    # yazabilirdi (ilk kontrolun `not captured_cards_body` kismi o an HALA
    # True olurdu). Bagimsiz `if` + capa'li kart-listesi isareti, bu sirayla
    # da doğru davranmalıdır - aciklama yaniti asla kart-listesi olarak
    # yanlis siniflandirilmamalidir.
    cards_body = _cards_response_body(
        {
            "job_id": "555",
            "title": "Title",
            "company": "Company",
            "location": "Istanbul",
            "time_at": 1785694003000,
        }
    )
    descriptions_body = _descriptions_response_body({"555": "Real description text."})
    _install_fake_playwright(
        monkeypatch,
        response_events=[
            (_DESCRIPTIONS_RESPONSE_URL, descriptions_body),
            (_CARDS_RESPONSE_URL, cards_body),
        ],
    )

    (result,) = fetch_search_results_page(profile_dir, "Istanbul", '"Sales"', 0)

    assert 'data-job-id="555"' in result
    assert 'data-field="description">Real description text.<' in result


# ---------------------------------------------------------------------------
# Yardimci fonksiyonlarin dogrudan testleri (M10.2 mimari evrimi) - JSON
# ayristirma mantigi, tam `fetch_search_results_page()` akisindan izole
# test edilebilir olacak kadar onemlidir.
# ---------------------------------------------------------------------------


def test_job_id_from_jobposting_urn_extracts_the_numeric_suffix():
    assert _job_id_from_jobposting_urn("urn:li:fsd_jobPosting:4445853687") == "4445853687"


def test_format_listed_date_converts_epoch_milliseconds_to_iso_date():
    assert _format_listed_date(1785694003000) == "2026-08-02"


def test_parse_job_cards_response_extracts_all_fields_in_element_order():
    body = _cards_response_body(
        {
            "job_id": "2",
            "title": "Second",
            "company": "Company B",
            "location": "Ankara",
            "time_at": 1785694003000,
        },
        {
            "job_id": "1",
            "title": "First",
            "company": "Company A",
            "location": "Istanbul",
            "time_at": 1786000000000,
        },
    )

    cards = _parse_job_cards_response(body)

    # `data.elements[]`in SIRASI korunur - `included[]`in kendi sirasi
    # DEGIL (bkz. `_parse_job_cards_response()`'in kendi dokumani).
    assert [c["job_id"] for c in cards] == ["2", "1"]
    assert cards[0]["title"] == "Second"
    assert cards[0]["company"] == "Company B"
    assert cards[0]["location"] == "Ankara"
    assert cards[0]["date"] == "2026-08-02"


def test_parse_job_cards_response_date_is_empty_string_when_no_listed_date_item():
    body = _cards_response_body(
        {"job_id": "1", "title": "T", "company": "C", "location": "L", "time_at": None}
    )

    cards = _parse_job_cards_response(body)

    assert cards[0]["date"] == ""


def test_parse_job_cards_response_returns_empty_list_for_zero_elements():
    import json

    body = json.dumps({"data": {"elements": []}, "included": []})

    assert _parse_job_cards_response(body) == []


def test_parse_job_cards_response_skips_an_element_with_no_matching_included_card():
    import json

    body = json.dumps(
        {
            "data": {
                "elements": [
                    {
                        "jobCardUnion": {
                            "*jobPostingCard": "urn:li:fsd_jobPostingCard:(999,JOBS_SEARCH)"
                        }
                    }
                ]
            },
            "included": [],
        }
    )

    assert _parse_job_cards_response(body) == []


def test_parse_job_descriptions_response_maps_job_id_to_description_text():
    body = _descriptions_response_body({"1": "First description.", "2": "Second description."})

    descriptions = _parse_job_descriptions_response(body)

    assert descriptions == {"1": "First description.", "2": "Second description."}


def test_parse_job_descriptions_response_returns_empty_dict_for_no_entities():
    import json

    body = json.dumps({"included": []})

    assert _parse_job_descriptions_response(body) == {}


def test_build_synthetic_card_html_includes_job_id_and_all_field_attributes():
    result = _build_synthetic_card_html(
        job_id="555",
        title="Sales Executive",
        company="Acme Corp",
        location="Istanbul, Turkey",
        date="2026-04-01",
        description="We are hiring.",
        link="https://www.linkedin.com/jobs/view/555/",
    )

    assert 'data-job-id="555"' in result
    for field, value in (
        ("title", "Sales Executive"),
        ("company", "Acme Corp"),
        ("location", "Istanbul, Turkey"),
        ("date", "2026-04-01"),
        ("description", "We are hiring."),
    ):
        assert f'data-field="{field}">{value}<' in result
    assert 'data-field="link" href="https://www.linkedin.com/jobs/view/555/"' in result


# ---------------------------------------------------------------------------
# Regresyon fixture'lari (M10.2 mimari evrimi, bagimsiz talimat: "future
# LinkedIn API changes fail in tests instead of silently producing zero
# collected jobs"). Bu fixture'lar, LinkedIn'in GERCEK
# voyagerJobsDashJobCards / jobPostingDetailDescription yanitlarinin (bir
# gercek hesaba karsi ampirik olarak dogrulanan) YAPISAL sekliyle
# ANONIMLESTIRILMIS bir kopyasidir - bkz.
# tests/unit/adapters/linkedin/fixtures/.
# ---------------------------------------------------------------------------


def test_regression_real_job_cards_response_extracts_all_fields():
    body = (_FIXTURES_DIR / "job_cards_response.json").read_text(encoding="utf-8")

    cards = _parse_job_cards_response(body)

    assert [c["job_id"] for c in cards] == ["1000000001", "1000000002", "1000000003"]
    assert cards[0]["title"] == "Örnek Analist Pozisyonu"
    assert cards[0]["company"] == "Örnek Holding A.Ş."
    assert cards[0]["location"] == "İstanbul, Türkiye (İş yerinde)"
    assert cards[0]["date"] == "2026-08-02"
    # Ikinci ilan bilerek LISTED_DATE'siz - sabit bir alan varsayimi
    # YERINE dogru sekilde bos dize donmelidir.
    assert cards[1]["date"] == ""


def test_regression_real_job_descriptions_response_extracts_description_text():
    body = (_FIXTURES_DIR / "job_descriptions_response.json").read_text(encoding="utf-8")

    descriptions = _parse_job_descriptions_response(body)

    assert set(descriptions.keys()) == {"1000000001", "1000000002"}
    assert "Örnek Holding A.Ş." in descriptions["1000000001"]
    assert len(descriptions["1000000001"]) > 100
    # Ucuncu ilan (1000000003) bilerek fixture'da YOK - o ilan icin
    # aciklamanin dogru sekilde bulunamadigini (KeyError DEGIL) kanitlar.
    assert "1000000003" not in descriptions
