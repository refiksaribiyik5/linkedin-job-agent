"""`launch_persistent_context()` ile GERCEK Chromium kullanarak, Faz 13'un
mimari iddiasini ("cold snapshot replay" DEGIL, kalici profil) kod
seviyesinde DEGIL, GERCEK tarayici davranisi uzerinden kanitlayan canli
entegrasyon testi.

`tests/unit/adapters/linkedin/test_playwright_client.py`'nin aksine (
`sync_playwright` tamamen sahtelenir) bu dosya GERCEK bir Chromium ikili
dosyasi baslatir - ama LinkedIn'e (ya da BASKA herhangi bir adrese)
HICBIR ZAMAN network istegi gonderilmez: yalnizca `context.add_cookies()`/
`context.cookies()` (saf CDP cagrilari, hicbir sayfaya GIT'MEDEN calisir)
kullanilir.

`ANTHROPIC_API_KEY` icin `tests/integration/llm/test_anthropic_adapter_live.py`'nin
izledigi AYNI "gercek bagimlilik yoksa ATLA" ilkesi: Chromium ikili
dosyasi kurulu degilse (`playwright install chromium` calistirilmamissa)
bu test ATLANIR - CI/baska bir makinede Chromium kurulu olmayabilir.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


def test_persistent_profile_survives_context_close_and_reopen(tmp_path: Path):
    # `browser-profile/<account_id>/` deseniyle tutarli, hesap-bazli bir
    # profil dizini simule edilir - ama GERCEK bir hesap/LinkedIn ile
    # hicbir ilgisi yoktur (bkz. modul dokumani).
    profile_dir = tmp_path / "browser-profile" / "test-account-id"
    # Playwright'in `add_cookies()`'i icin GERCEK bir ag istegi
    # GEREKTIRMEYEN, sabit bir URL - yalnizca cerezin hangi origin'e ait
    # oldugunu belirtmek icin kullanilir, bu adrese HICBIR ZAMAN GIDILMEZ.
    # `expires` ACIKCA (uzak bir gelecek Unix zaman damgasi) verilir - AKSI
    # HALDE Chromium bunu bir SESSION cerezi sayar (tarayici KAPANINCA
    # silinmesi standart, KENDI kodumuzla ilgisiz bir davranistir) ve
    # `context.close()` sonrasi KASITLI OLARAK diskte KALICI OLMAZ - bu
    # testin "kalicilik" iddiasini yanlislikla CURUTURDU.
    test_cookie = {
        "name": "round_trip_test_cookie",
        "value": "persisted-across-reopen",
        "url": "http://persistent-profile-test.invalid",
        "expires": 4102444800,  # 2100-01-01T00:00:00Z
    }

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(str(profile_dir), headless=True)
            try:
                context.add_cookies([test_cookie])
            finally:
                context.close()
    except Exception as exc:  # noqa: BLE001 - Chromium kurulu degilse ATLA
        pytest.skip(
            f"Gercek Chromium baslatilamadi (`playwright install chromium` "
            f"calistirilmis mi?) - canli tarayici entegrasyon testi atlanir: {exc}"
        )

    # Profil dizini GERCEKTEN diske yazildi (madde: "persistent profile
    # gercekten olusmus olmali").
    assert profile_dir.exists()

    # IKINCI, TAMAMEN AYRI bir `launch_persistent_context()` cagrisi - bu,
    # ONCEKI mimarinin ("storage_state cikar, YENI bos bir context'e
    # enjekte et") YAPAMAYACAGI seyi kanitlar: burada hicbir cerez degeri
    # elle tasinmiyor, yalnizca AYNI dizin yolu tekrar acilyor.
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(str(profile_dir), headless=True)
        try:
            cookies = context.cookies()
        finally:
            context.close()

    matching = [c for c in cookies if c["name"] == "round_trip_test_cookie"]
    assert len(matching) == 1, (
        "Cerez, KAPATILIP YENIDEN ACILAN ayni persistent profilde HALA mevcut "
        "olmali - bu, 'cold snapshot replay' (her seferinde bos context) "
        "mimarisinden GERCEKTEN farkli oldugunu kanitlayan asil test."
    )
    assert matching[0]["value"] == "persisted-across-reopen"
