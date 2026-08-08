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
    LoginTimeoutError,
    perform_interactive_login,
)


class _FakePage:
    def __init__(self, raise_on_wait: Exception | None = None):
        self.goto_calls: list[str] = []
        self.wait_for_url_calls: list[tuple[str, int]] = []
        self._raise_on_wait = raise_on_wait

    def goto(self, url: str) -> None:
        self.goto_calls.append(url)

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

    def new_context(self) -> _FakeContext:
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


def _install_fake_playwright(monkeypatch, *, raise_on_wait: Exception | None = None):
    page = _FakePage(raise_on_wait=raise_on_wait)
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
