"""playwright_client.py icin birim testleri (Roadmap M3.1).

Gercek bir tarayici/LinkedIn'e HICBIR ZAMAN dokunulmaz - `sync_playwright`
tamamen sahtelenir (monkeypatch). Bu, hem CI'da calisabilmesini hem de
"kullanicinin kendi kimlik bilgilerini dogrudan tarayiciya girdigi"
tasarim kararinin (proje talimatiyla onaylandi) test edilebilir tek yolu
olmasini saglar - gercek bir insan mudahalesi gerektiren akisi otomatik
test etmenin baska bir yolu yoktur.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from linkedinbot.adapters.linkedin import playwright_client as module_under_test
from linkedinbot.adapters.linkedin.playwright_client import (
    LOGIN_URL,
    SESSION_CHECK_URL,
    LoginTimeoutError,
    check_session_is_valid,
    perform_interactive_login,
)


class _FakePage:
    def __init__(
        self,
        raise_on_wait: Exception | None = None,
        landing_url: str | None = None,
        raise_on_goto: Exception | None = None,
    ):
        self.goto_calls: list[str] = []
        self.wait_for_url_calls: list[tuple[str, int]] = []
        self._raise_on_wait = raise_on_wait
        self._landing_url = landing_url
        self._raise_on_goto = raise_on_goto
        self.url = ""

    def goto(self, url: str) -> None:
        self.goto_calls.append(url)
        if self._raise_on_goto is not None:
            raise self._raise_on_goto
        self.url = self._landing_url if self._landing_url is not None else url

    def wait_for_url(self, pattern: str, timeout: int) -> None:
        self.wait_for_url_calls.append((pattern, timeout))
        if self._raise_on_wait is not None:
            raise self._raise_on_wait


class _FakeContext:
    def __init__(self, page: _FakePage):
        self._page = page
        self.storage_state_return = {"cookies": [{"name": "li_at", "value": "fake-session"}]}

    def new_page(self) -> _FakePage:
        return self._page

    def storage_state(self) -> dict:
        return self.storage_state_return


class _FakeBrowser:
    def __init__(self, context: _FakeContext):
        self._context = context
        self.closed = False
        self.new_context_kwargs: dict | None = None

    def new_context(self, **kwargs) -> _FakeContext:
        self.new_context_kwargs = kwargs
        return self._context

    def close(self) -> None:
        self.closed = True


class _FakeChromium:
    def __init__(self, browser: _FakeBrowser):
        self._browser = browser
        self.launch_kwargs: dict | None = None

    def launch(self, **kwargs) -> _FakeBrowser:
        self.launch_kwargs = kwargs
        return self._browser


class _FakePlaywright:
    def __init__(self, chromium: _FakeChromium):
        self.chromium = chromium


def _install_fake_playwright(
    monkeypatch,
    *,
    raise_on_wait: Exception | None = None,
    landing_url: str | None = None,
    raise_on_goto: Exception | None = None,
):
    page = _FakePage(
        raise_on_wait=raise_on_wait, landing_url=landing_url, raise_on_goto=raise_on_goto
    )
    context = _FakeContext(page)
    browser = _FakeBrowser(context)
    chromium = _FakeChromium(browser)
    playwright_obj = _FakePlaywright(chromium)

    @contextmanager
    def _fake_sync_playwright():
        yield playwright_obj

    monkeypatch.setattr(module_under_test, "sync_playwright", _fake_sync_playwright)
    return page, context, browser, chromium


def test_perform_interactive_login_launches_headed_browser(monkeypatch):
    # "headless=False" kritik - kullanicinin GORUP kendi kimlik bilgilerini
    # girebilecegi bir pencere olmadan interaktif giris imkansizdir.
    _page, _context, _browser, chromium = _install_fake_playwright(monkeypatch)

    perform_interactive_login()

    assert chromium.launch_kwargs == {"headless": False}


def test_perform_interactive_login_navigates_to_linkedin_login_page(monkeypatch):
    page, _context, _browser, _chromium = _install_fake_playwright(monkeypatch)

    perform_interactive_login()

    assert page.goto_calls == [LOGIN_URL]


def test_perform_interactive_login_waits_for_authenticated_redirect(monkeypatch):
    page, _context, _browser, _chromium = _install_fake_playwright(monkeypatch)

    perform_interactive_login()

    assert len(page.wait_for_url_calls) == 1
    pattern, timeout = page.wait_for_url_calls[0]
    assert "feed" in pattern
    assert timeout > 0


def test_perform_interactive_login_returns_storage_state_on_success(monkeypatch):
    _page, context, _browser, _chromium = _install_fake_playwright(monkeypatch)

    result = perform_interactive_login()

    assert result == context.storage_state_return


def test_perform_interactive_login_closes_browser_after_success(monkeypatch):
    _page, _context, browser, _chromium = _install_fake_playwright(monkeypatch)

    perform_interactive_login()

    assert browser.closed is True


def test_perform_interactive_login_raises_login_timeout_error_on_timeout(monkeypatch):
    _page, _context, _browser, _chromium = _install_fake_playwright(
        monkeypatch, raise_on_wait=PlaywrightTimeoutError("Timeout 300000ms exceeded")
    )

    with pytest.raises(LoginTimeoutError):
        perform_interactive_login()


def test_perform_interactive_login_closes_browser_even_on_timeout(monkeypatch):
    # Ic-denetim odakli test: tarayici penceresi acik birakilirsa (orn.
    # kullanici 2FA'yi tamamlamazsa) surec sonsuza kadar asili kalan bir
    # tarayici surecine neden olabilir - try/finally bunu onlemeli.
    _page, _context, browser, _chromium = _install_fake_playwright(
        monkeypatch, raise_on_wait=PlaywrightTimeoutError("Timeout 300000ms exceeded")
    )

    with pytest.raises(LoginTimeoutError):
        perform_interactive_login()

    assert browser.closed is True


def test_perform_interactive_login_timeout_message_is_actionable(monkeypatch):
    # Ham Playwright TimeoutError'i ("Timeout 300000ms exceeded") "ne
    # bekleniyordu" baglami tasimaz - kullaniciya giris/2FA'nin
    # tamamlanmadigini acikca soyleyen bir mesaj gerekir.
    _page, _context, _browser, _chromium = _install_fake_playwright(
        monkeypatch, raise_on_wait=PlaywrightTimeoutError("Timeout 300000ms exceeded")
    )

    with pytest.raises(LoginTimeoutError, match="giris"):
        perform_interactive_login()


# ---------------------------------------------------------------------------
# check_session_is_valid (Roadmap M3.2) - kayitli bir storage_state'in HALA
# gecerli olup olmadigini, insan mudahalesi olmadan (headless), canli olarak
# kontrol eder. M3.1'in interaktif giris akisindan farkli olarak burada
# beklenen bir "insan tamamlar" adimi yoktur - ya oturum kabul edilir ya da
# edilmez, sonuc `goto()` tamamlaninca zaten bellidir.
# ---------------------------------------------------------------------------

FAKE_STORED_STATE = {"cookies": [{"name": "li_at", "value": "previously-stored-session"}]}


def test_check_session_is_valid_launches_headless_browser(monkeypatch):
    # M3.1'in aksine burada hicbir insan mudahalesi beklenmez - gorunur bir
    # pencereye gerek yoktur.
    _page, _context, _browser, chromium = _install_fake_playwright(
        monkeypatch, landing_url=SESSION_CHECK_URL
    )

    check_session_is_valid(FAKE_STORED_STATE)

    assert chromium.launch_kwargs == {"headless": True}


def test_check_session_is_valid_loads_the_given_storage_state(monkeypatch):
    _page, _context, browser, _chromium = _install_fake_playwright(
        monkeypatch, landing_url=SESSION_CHECK_URL
    )

    check_session_is_valid(FAKE_STORED_STATE)

    assert browser.new_context_kwargs == {"storage_state": FAKE_STORED_STATE}


def test_check_session_is_valid_navigates_to_session_check_url(monkeypatch):
    page, _context, _browser, _chromium = _install_fake_playwright(
        monkeypatch, landing_url=SESSION_CHECK_URL
    )

    check_session_is_valid(FAKE_STORED_STATE)

    assert page.goto_calls == [SESSION_CHECK_URL]


def test_check_session_is_valid_returns_true_when_still_on_authenticated_page(monkeypatch):
    _page, _context, _browser, _chromium = _install_fake_playwright(
        monkeypatch, landing_url=SESSION_CHECK_URL
    )

    assert check_session_is_valid(FAKE_STORED_STATE) is True


def test_check_session_is_valid_returns_false_when_redirected_to_login(monkeypatch):
    # Sunucu tarafinda gecersiz/suresi dolmus bir oturum, LinkedIn'i
    # dogrudan giris sayfasina yonlendirmeye zorlar - bu, "invalidate the
    # session by deleting a cookie" (Roadmap M3.2 Tamamlanma Dogrulamasi)
    # senaryosunun canli davranis karsiligidir.
    _page, _context, _browser, _chromium = _install_fake_playwright(
        monkeypatch, landing_url="https://www.linkedin.com/login"
    )

    assert check_session_is_valid(FAKE_STORED_STATE) is False


def test_check_session_is_valid_closes_browser_after_check(monkeypatch):
    _page, _context, browser, _chromium = _install_fake_playwright(
        monkeypatch, landing_url=SESSION_CHECK_URL
    )

    check_session_is_valid(FAKE_STORED_STATE)

    assert browser.closed is True


def test_check_session_is_valid_closes_browser_even_if_navigation_fails(monkeypatch):
    _page, _context, browser, _chromium = _install_fake_playwright(
        monkeypatch, raise_on_goto=RuntimeError("simulated network failure")
    )

    with pytest.raises(RuntimeError, match="simulated network failure"):
        check_session_is_valid(FAKE_STORED_STATE)

    assert browser.closed is True


def test_check_session_is_valid_does_not_reclassify_navigation_errors(monkeypatch):
    # Onemli ayrim (TDD Section 20: TransientError vs PermanentError): bir
    # ag/navigasyon hatasi "oturum gecersiz" DEGILDIR - bu iki ayri hata
    # sinifidir. check_session_is_valid() bir navigasyon hatasini
    # SESSIZCE False'a cevirmemeli/yutmamalidir; ham hata oldugu gibi
    # yukari sizmalidir (siniflandirma cagiranin/gelecekteki M9.3'un isidir).
    _page, _context, _browser, _chromium = _install_fake_playwright(
        monkeypatch, raise_on_goto=RuntimeError("simulated network failure")
    )

    with pytest.raises(RuntimeError, match="simulated network failure"):
        check_session_is_valid(FAKE_STORED_STATE)
