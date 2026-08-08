"""Playwright ile LinkedIn'e tek seferlik interaktif giris (Roadmap M3.1).

GUVENLIK KARARI (proje talimatiyla acikca onaylanmis): kullanicinin
LinkedIn parolasi bu kod tarafindan HICBIR ZAMAN okunmaz/islenmez/saklanmaz.
Bu modul yalnizca GORUNUR (`headless=False`) bir tarayici penceresi acar,
LinkedIn'in giris sayfasina yonlendirir ve kullanicinin KENDI kimlik
bilgilerini dogrudan tarayiciya girip (ve varsa 2FA/CAPTCHA'yi
tamamlayip) basariyla giris yapmasini bekler. Parola/kullanici adi icin
hicbir parametre, ortam degiskeni veya interaktif terminal istemi
YOKTUR - TDD Section 24'un "parola hicbir zaman diske yazilmaz" karari,
parolanin bu surece hic girmemesiyle YAPISAL olarak (bir disipline degil,
bir imkansizliga dayanarak) saglanir.

Basarili girisin tespiti: LinkedIn'in giris sonrasi yonlendirdigi "feed"
(ana akis) sayfasina ulasilmasi beklenir (`_AUTHENTICATED_URL_PATTERN`).
Kullanici cok uzun sure giris sayfasinda kalirsa/vazgecerse (2FA
tamamlanmaz, tarayici kapatilir vb.), `LoginTimeoutError` firlatilir -
Playwright'in kendi ham `TimeoutError`'i "ne bekleniyordu" baglamini
tasimaz.
"""

from __future__ import annotations

from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://www.linkedin.com/login"
_AUTHENTICATED_URL_PATTERN = "**/feed/**"
# 5 dakika - kullanicinin 2FA/CAPTCHA tamamlamasi icin makul, cömert bir sure
# (Roadmap M3.1 "gercek giris akisinda beklenmedik surtunme olasidir").
_LOGIN_TIMEOUT_MS = 5 * 60 * 1000


class LoginTimeoutError(RuntimeError):
    """Kullanici, `_LOGIN_TIMEOUT_MS` icinde interaktif girisi
    tamamlamadi (ana akis sayfasina ulasilamadi)."""


def perform_interactive_login() -> dict[str, Any]:
    """Gorunur bir tarayici acar, kullanicinin interaktif olarak giris
    yapmasini bekler, basarili giris sonrasi Playwright `storage_state`'i
    (cerezler + local storage) dondurur.

    Tarayici, basarili/basarisiz her durumda kapatilir (try/finally) -
    aksi halde bir zaman asimi/hata, arka planda asili kalan bir tarayici
    surecine (kaynak sizintisi) neden olabilirdi.
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(LOGIN_URL)
            try:
                page.wait_for_url(_AUTHENTICATED_URL_PATTERN, timeout=_LOGIN_TIMEOUT_MS)
            except PlaywrightTimeoutError as exc:
                raise LoginTimeoutError(
                    "Interaktif LinkedIn girisi zaman asimina ugradi - "
                    f"{_LOGIN_TIMEOUT_MS // 1000} saniye icinde ana akis "
                    "sayfasina ulasilamadi (giris tamamlanmadi mi, 2FA/CAPTCHA "
                    "yarim mi kaldi?)."
                ) from exc
            return context.storage_state()
        finally:
            browser.close()
