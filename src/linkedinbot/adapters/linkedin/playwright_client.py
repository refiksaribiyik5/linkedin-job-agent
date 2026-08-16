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

M3.2 (Roadmap "Oturum Dogrulama", FR-1) `check_session_is_valid()`'i
ekler: kayitli bir `storage_state`'in HALA gecerli olup olmadigini,
insan mudahalesi olmadan (headless), canli olarak LinkedIn'e karsi
kontrol eder. `perform_interactive_login()`'den farki - burada beklenen
bir "insan tamamlar" adimi yoktur; sonuc, kimlik dogrulama gerektiren
bir sayfaya gidildiginde (sunucu tarafinda ANINDA redirect ile) zaten
bellidir, bu yuzden `wait_for_url` ile bir sey "beklemeye" gerek yoktur.
Bir ag/navigasyon hatasi (orn. zaman asimi, DNS) BILEREK "gecersiz
oturum" olarak yeniden siniflandirilmaz/yutulmaz - bu, TDD Section
20'nin ayirdigi iki farkli hata sinifidir (TransientError vs
PermanentError); byle bir hata oldugu gibi yukari sizar.

M3.3 (Roadmap "Arama & Sayfalama", FR-21) `fetch_search_results_page()`'i
ekler: kalici bir `storage_state`'i kullanarak, verilen (location,
keywords) sorgusu icin LinkedIn is arama sonuclarinin TEK bir sayfasindaki
ham ilan karti HTML'lerini doner. Sayfalama MANTIGI (kac sayfa gidilecegi,
FR-21'in ust siniri, `collection_capped` bayragi) BURADA YOKTUR - proje
talimatiyla acikca onaylandigi gibi bu, `collection/collector.py`'nin
(PaginationController) sorumlulugudur; bu fonksiyon Playwright'in
kendisiyle ilgili SAF bir altyapi ilkelidir (tek sayfa getir, ham
HTML'leri don), TDD Section 6'nin `collection` modulunu yalnizca
`linkedin_port`'a bagimli kilma karariyla tutarli - gercek Playwright
detaylari `collection/collector.py`'ye hicbir zaman sizmaz.

BILINEN SINIRLAMA (M3.1/M3.2'nin ayni dipnotu burada da gecerlidir, M10.2'de
canli olarak dogrulanip duzeltildi - bkz. asagidaki "M10.2 duzeltmesi"):
`SEARCH_URL`/`_JOB_CARD_SELECTOR`, LinkedIn'in GERCEK, GUNCEL DOM/URL
yapisina karsi CANLI olarak dogrulanamamisti (bu kod ilk yazildiginda
gercek bir LinkedIn hesabina/tarayiciya erisim yoktu - Roadmap M3.3'un
kendi "Tahmini Sure" notu da "LinkedIn'in DOM/secici kirilganligi en buyuk
risk" der).

M10.2 duzeltmesi (bagimsiz incelemede bulunan, gercek hesaba karsi ampirik
olarak dogrulanmis bir bulgu - yukaridaki "BILINEN SINIRLAMA" notunun
ONGORDUGU tam senaryo): M10.2'nin ilk gercek Bootstrap calistirmasi
jobs_collected=0 uretti - eski _JOB_CARD_SELECTOR ("div.job-card-container")
ve eski alan-bazli secicilerin (collector.py) hicbirinin LinkedIn'in GUNCEL
DOM'unda karsiligi yoktu. Kok neden: LinkedIn artik anlamsiz, derleme-bazli
hash'lenmis CSS sinifi adlari (orn. "_88f38042") kullaniyor - bunlar hicbir
sekilde guvenilir bir secici olamaz (her derlemede degisir). Canli DOM'un
kapsamli incelenmesiyle (kullanicinin gercek, gecerli oturumuna karsi,
salt-okunur tanilama) dogrulanan, hash'lenmemis, anlamsal/erisebilirlik
temelli yeni strateji:

- Kart siniri: componentkey="job-card-component-ref-<jobId>" - LinkedIn'in
  kendi bilesen-izleme ozniteligi, gercek sayisal ilan ID'sini dogrudan
  tasir (hash degil). [role="button"] ile birlestirilir - ayni componentkey
  degerini paylasan bir ic-ice yinelenen sarmalayici div'i (yalnizca dis,
  tiklanabilir div bunu tasir) elemek icin - bu olmadan her ilan iki kez
  sayilirdi (ampirik olarak dogrulandi: 50 ham eslesme / 25 gercek ilan).
- Baglanti: kart icinde hicbir <a href> yoktur (kart, JS-tetiklenen bir
  div[role=button]'dur) - bunun yerine LinkedIn'in dogrulanmis kalici URL
  kalibi kullanilarak componentkey'den cikarilan ID'den dogrudan insa
  edilir: https://www.linkedin.com/jobs/view/{job_id}/.
- Baslik/Sirket/Lokasyon: kartin gorunur metin dugumlerinin (aria-hidden
  dahil, hicbir alan-bazli aria-*/data-*/id/itemprop ozniteligi yoktur -
  kapsamli bir oznitelik envanteriyle dogrulandi) sirali konumuyla cikarilir:
  ilk (yinelenen "dogrulanmis ilan" duyurusu metni tekrarlari bastirilarak)
  baslik, ondan sonraki sirket, ondan sonraki lokasyon - kartlar arasi
  hicbir metin araya girmedigi icin bu uc alan icin guvenli (25 gercek
  kart uzerinde dogrulandi).
- Tarih: sabit bir sira-konumuyla degil, goreli-zaman kalibina uyan
  (_RELATIVE_DATE_PATTERN) ilk metinle eslestirilerek bulunur - lokasyon
  ile tarih arasindaki "basvuran sayisi"/"Kolay Basvuru" gibi rozet
  metinlerinin varligi/sayisi ayni sayfadaki farkli kartlar arasinda bile
  degiskendir (25 kartin tamami uzerinde ampirik olarak dogrulandi - orn.
  bazi kartlarda rozet yok, bazilarinda bir rozet var) - sabit bir sira-
  indeksi bugun bile yanlis olurdu, yalniz gelecekte degil.
- Aciklama: kart listesinde hicbir sekilde mevcut degildir (4+ farkli
  karttan tam metin dokumu alinarak dogrulandi) - ama arama sonuclari
  sayfasi zaten sectigi ilanin detay panelini yukler (ilk ilan sayfa
  yuklenirken otomatik secilir); bir karta tiklamak bu paneli tam sayfa
  yenileme olmadan (URL/baslik degisir ama page.goto() yoktur - ampirik
  olarak dogrulandi, ~4sn'de yerlesir) gunceller. Aciklama, ayni
  componentkey kaliniyla: componentkey="JobDetails_AboutTheJob_<jobId>"
  adresinden okunur. Bu, "her ilanin kendi sayfasini ziyaret et"
  tasarimina (mimari genisleme gerektirirdi - yeni Port metodu, TDD
  Section 22 hiz sinirlayici kapsam degisikligi) gore tercih edildi:
  sayfa-basi navigasyon sayisi degismez (halen 1), yalnizca sayfa-ici
  etkilesim eklenir.

Mimari sinir (kasitli, kullanicidan acikca onaylandi): butun bu LinkedIn-
DOM-ozel mantik (yukaridaki 5 madde) BU DOSYADA, fetch_search_results_page()
icinde yasar. Fonksiyon, LinkedIn'in kendi (kirilgan) HTML'ini asla
disariya sizdirmaz - bunun yerine, her ilan icin bizim tanimladigimiz,
kararli bir sentetik HTML parcasi (data-job-id + alan basina data-field
oznitelikleri) uretir ve onu doner. collection/collector.py (M3.4) bununla
calisir - LinkedIn'in kendi sinif adlarini/yapisini artik hicbir zaman
gormez. Sonuc: LinkedIn DOM'unu yeniden degistirirse, hata yalnizca bu
dosyada olusur - collector.py, extract_record(), asagi akis butun pipeline
(normalizasyon/filtreleme/skorlama) degismeden kalir. Bu, Ports & Adapters'in
tam da amacladigi izolasyondur - yeni bir Port/Roadmap degisikligi
GEREKTIRMEZ (mevcut search_jobs_page(...) -> list[str] imzasi aynen korunur).

Ic-denetimde bilerek cozulmeyen bir sinirlama: sabit bir fixture'a karsi
regresyon testleri (bkz. test_playwright_client.py) bu dosyanin kendi
mantigindaki gerilemeleri yakalar, ama LinkedIn'in gelecekte DOM'unu tekrar
degistirmesini otomatik olarak tespit edemez - bu, herhangi bir kazima
sisteminin dogasinda olan, insan-dogrulamali bir donguyu (bu M10.2
duzeltmesinin kendisinin izledigi surec) gerektiren bir sinirlamadir.
"""

from __future__ import annotations

import contextlib
import html as html_module
import json
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://www.linkedin.com/login"
SESSION_CHECK_URL = "https://www.linkedin.com/feed/"
SEARCH_URL = "https://www.linkedin.com/jobs/search/"
_AUTHENTICATED_URL_PATTERN = "**/feed/**"
# 5 dakika - kullanicinin 2FA/CAPTCHA tamamlamasi icin makul, cömert bir sure
# (Roadmap M3.1 "gercek giris akisinda beklenmedik surtunme olasidir").
_LOGIN_TIMEOUT_MS = 5 * 60 * 1000
# LinkedIn'in is arama sonuc sayfasinin (bilinen, ama canli dogrulanmamis)
# geleneksel sayfalama boyutu - `start` parametresi bu birimde ilerler.
_RESULTS_PER_PAGE = 25
_JOB_VIEW_URL_TEMPLATE = "https://www.linkedin.com/jobs/view/{job_id}/"
# LinkedIn'in kendi (belgesiz) Voyager API'sinin URL'lerinde gecen, kart
# listesini/aciklama metnini tasiyan yanitlari tanimlayan alt-dizeler -
# bkz. modul dokumaninin "M10.2 mimari evrimi" notu.
#
# M10.2 duzeltmesi (canli olarak dogrulanan bir bulgu): kart listesi
# ENDPOINT'inin REST.li kaynak yolu "/api/voyagerJobsDashJobCards?" - ama
# aciklama metnini tasiyan GraphQL yanitinin URL'si de bu TAM AYNI alt-dizeyi
# BASKA bir yerde (kendi `queryId=voyagerJobsDashJobCards.<hash>` parametresinde,
# LinkedIn'in bu GraphQL sorgusuna verdigi isim yuzunden) icerir - canli bir
# hesaba karsi ampirik olarak dogrulandi. Eski `"voyagerJobsDashJobCards" in url`
# kontrolu bu yuzden aciklama yanitini da (yanlislikla) esleyip, `elif` sirasi
# nedeniyle SESSIZCE dusuruyordu (bkz. asagidaki `_on_response()` dokumani).
# Duzeltme: kart listesi ISARETI, sadece GERCEK REST.li kaynak yoluna
# (`/api/<isim>?` - yani isim SORGU PARAMETRESI DEGIL, YOLUN KENDISI) ozgu
# olacak sekilde CAPA'landirilir - GraphQL uc noktasi HER ZAMAN `/api/graphql?`
# uzerinden gelir, bu yuzden bu capa GraphQL yanitlariyla asla eslesmez.
_JOB_CARDS_RESPONSE_URL_MARKER = "/api/voyagerJobsDashJobCards?"
_JOB_DETAIL_DESCRIPTION_RESPONSE_URL_MARKER = "jobPostingDetailDescription"
_JOB_CARD_ENTITY_TYPE = "com.linkedin.voyager.dash.jobs.JobPostingCard"
_JOB_DESCRIPTION_ENTITY_TYPE = "com.linkedin.voyager.dash.jobs.JobDescription"
# Her ilan IKI JobPostingCard varyantinda gelir (ayni is icin) - yalnizca
# arama-listesi varyanti (kartlarin GORUNTULEME SIRASINI tasiyan
# `data.elements[]` tarafindan referans verilen) kullanilir.
_JOB_CARD_SEARCH_VARIANT_SUFFIX = "JOBS_SEARCH)"
_LISTED_DATE_FOOTER_ITEM_TYPE = "LISTED_DATE"
# Ag yanitlarinin (goto() sonrasi ASENKRON olarak gelir) yerlesmesi icin
# makul, comert ust sinirlar - ampirik olarak gozlemlenen (~4-6sn)
# gecikmenin uzerinde.
_JOB_CARDS_RESPONSE_TIMEOUT_MS = 20 * 1000
_JOB_DESCRIPTIONS_RESPONSE_TIMEOUT_MS = 20 * 1000
_RESPONSE_POLL_INTERVAL_MS = 250

class LoginTimeoutError(RuntimeError):
    """Kullanici, `_LOGIN_TIMEOUT_MS` icinde interaktif girisi
    tamamlamadi (ana akis sayfasina ulasilamadi)."""


class JobCardsResponseTimeoutError(RuntimeError):
    """M11.1 (Roadmap Faz 11, Toplama Anomali Tespiti): `_JOB_CARDS_RESPONSE_TIMEOUT_MS`
    icinde beklenen Job Cards ag yaniti hic gelmedi - `fetch_search_results_page()`
    KASITLI OLARAK bunu, LinkedIn'in gercekten bos bir sonuc kumesi
    dondurdugu (bir yanit geldi ama `_parse_job_cards_response()` sifir
    kart uretti) durumundan AYIRT eder: ikincisi hala `[]` doner (sayfalamanin
    dogal sonu icin GECERLI bir sinyal), ama bu istisna bir aktarim/erisim
    sorunudur ve `collector.py::_fetch_page_with_retry()`'nin (M9.4) mevcut
    `TransientError`/retry/devre-kesici zincirine (hicbir degisiklik
    GEREKMEDEN - `SessionInvalidError` DISINDAKI herhangi bir istisnayi
    zaten bu sekilde ele alir) dogrudan akar."""


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


def check_session_is_valid(storage_state: dict[str, Any]) -> bool:
    """Verilen `storage_state`'i (cerezler + local storage) yeni, gorunmez
    (`headless=True`) bir tarayici baglaminda yukleyip, kimlik dogrulama
    gerektiren bir LinkedIn sayfasina (`SESSION_CHECK_URL`) gidilerek
    oturumun HALA gecerli olup olmadigini kontrol eder.

    Gecersiz/suresi dolmus bir oturum, LinkedIn'i sunucu tarafinda
    dogrudan giris sayfasina yonlendirmeye zorlar - bu yuzden `goto()`
    tamamlandiktan hemen sonra `page.url`'nin hala kimlik dogrulanmis
    sayfada olup olmadigina bakmak yeterlidir; M3.1'deki gibi bir insanin
    tamamlamasini "beklemek" (wait_for_url/timeout) burada anlamsizdir.

    Tarayici, basarili/basarisiz her durumda kapatilir (try/finally).
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(storage_state=storage_state)
            page = context.new_page()
            page.goto(SESSION_CHECK_URL)
            return SESSION_CHECK_URL in page.url
        finally:
            browser.close()


def _job_id_from_jobposting_urn(urn: str) -> str:
    # "urn:li:fsd_jobPosting:4445853687" -> "4445853687"
    return urn.rsplit(":", 1)[-1]


def _format_listed_date(time_at_ms: float) -> str:
    """`LISTED_DATE` footer ogesinin epoch-milisaniye zaman damgasini
    (bkz. `_parse_job_cards_response()`) sabit, ISO-8601 tarih dizesine
    cevirir. `normalizer.py`'nin KENDI "posted_date, collected_at ile AYNI
    deger olarak KASITLI bir yer tutucudur" karari (M4.1, LinkedIn'in
    ONCEKI goreli-zaman metnini guvenilir sekilde ayristirmanin
    dogrulanamayan bicim varsayimlari gerektirecegi gerekcesiyle)
    DEGISTIRILMEMISTIR - bu fonksiyon yalnizca `RawJobRecord.posted_date`
    (M3.4, `Field(min_length=1)`) icin daha ONCEKINDEN daha kesin, sabit
    bir HAM deger uretir; normalizer'in bunu KULLANIP KULLANMAYACAGINA
    karar vermesi AYRI, gelecekteki bir kapsam sorusudur.
    """
    return datetime.fromtimestamp(time_at_ms / 1000, tz=UTC).strftime("%Y-%m-%d")


def _parse_job_cards_response(body: str) -> list[dict[str, str]]:
    """LinkedIn'in kendi (belgesiz) `voyagerJobsDashJobCards` API yanitini
    ayristirir - kart siniri/baslik/sirket/lokasyon/tarih icin
    ISIMLENDIRILMIS, YAPISAL JSON alanlari kullanir (DOM metin-sirasi
    tahmini veya CSS secicisi DEGIL - bkz. modul dokumaninin "M10.2
    mimari evrimi" notu).

    LinkedIn'in kendi REST.li koleksiyon semasi: `data.elements[]`in HER
    ogesi, `jobCardUnion["*jobPostingCard"]` araciligiyla `included[]`
    icindeki gercek `JobPostingCard` varligina isaret eden bir URN tasir -
    kartlarin GORUNTULEME SIRASI boylece `data.elements[]`in KENDI sirasiyla
    korunur (`included[]`in kendi sirasi guvenilir DEGILDIR). Her ilan IKI
    `JobPostingCard` varyantinda gelir (`JOBS_SEARCH` ve `JOB_DETAILS`, ayni
    is icin, ampirik olarak dogrulandi: 50 kart / 25 ilan) - yalnizca
    `data.elements[]`in referans verdigi (arama-listesi) varyant kullanilir.

    Beklenmedik/eksik bir alan (orn. `LISTED_DATE` footer ogesi yoksa) bu
    fonksiyonda ISTISNA FIRLATMAZ - ilgili deger bos dize kalir;
    `collector.py::extract_record()`'in KENDI "alan bulunamadi/bos" kontrolu
    (zaten var olan `PartialRecordError` yolu) bunu dogru sekilde ele alir.
    """
    payload = json.loads(body)
    included = payload.get("included") or []
    cards_by_urn = {
        item.get("entityUrn"): item
        for item in included
        if item.get("$type") == _JOB_CARD_ENTITY_TYPE
        and str(item.get("entityUrn", "")).endswith(_JOB_CARD_SEARCH_VARIANT_SUFFIX)
    }

    ordered_card_urns = [
        element.get("jobCardUnion", {}).get("*jobPostingCard")
        for element in (payload.get("data") or {}).get("elements") or []
    ]

    results: list[dict[str, str]] = []
    for card_urn in ordered_card_urns:
        card = cards_by_urn.get(card_urn)
        job_posting_urn = card.get("jobPostingUrn") if card else None
        if not card or not job_posting_urn:
            continue

        date_text = ""
        for footer_item in card.get("footerItems") or []:
            if footer_item.get("type") == _LISTED_DATE_FOOTER_ITEM_TYPE and footer_item.get(
                "timeAt"
            ):
                date_text = _format_listed_date(footer_item["timeAt"])
                break

        results.append(
            {
                "job_id": _job_id_from_jobposting_urn(job_posting_urn),
                "title": card.get("jobPostingTitle") or "",
                "company": ((card.get("primaryDescription") or {}).get("text")) or "",
                "location": ((card.get("secondaryDescription") or {}).get("text")) or "",
                "date": date_text,
            }
        )
    return results


def _parse_job_descriptions_response(body: str) -> dict[str, str]:
    """LinkedIn'in kendi `jobPostingDetailDescription` GraphQL yanitini
    ayristirir; `job_id -> aciklama metni` eslemesi doner. Ampirik olarak
    dogrulandi: bu TEK yanit, sayfadaki TUM ilanlarin (25/25) aciklamalarini
    (`JobDescription.descriptionText.text`, gercek 2-4 bin karakterlik
    metinler) tasir - `fetch_search_results_page()`'in eski (DOM tabanli)
    tasariminin gerektirdigi "her karta tikla" dongusu ARTIK GEREKMEZ.
    """
    payload = json.loads(body)
    included = payload.get("included") or []
    result: dict[str, str] = {}
    for item in included:
        if item.get("$type") != _JOB_DESCRIPTION_ENTITY_TYPE:
            continue
        job_posting_urn = item.get("*jobPosting")
        description_text = ((item.get("descriptionText") or {}).get("text")) or ""
        if not job_posting_urn or not description_text:
            continue
        result[_job_id_from_jobposting_urn(job_posting_urn)] = description_text
    return result


def _build_synthetic_card_html(
    job_id: str,
    title: str,
    company: str,
    location: str,
    date: str,
    description: str,
    link: str,
) -> str:
    """LinkedIn'in kendi (kirilgan) HTML'i YERINE, bizim tanimladigimiz,
    kararli bir sentetik parca uretir - `collection/collector.py`'nin ARTIK
    yalnizca BUNUNLA calismasi icin (bkz. modul dokumaninin "Mimari sinir"
    notu). `data-job-id` + alan basina `data-field` oznitelikleri disinda
    hicbir LinkedIn-ozel yapi tasimaz.
    """
    esc = html_module.escape
    return (
        f'<div data-job-id="{esc(job_id)}">'
        f'<span data-field="title">{esc(title)}</span>'
        f'<span data-field="company">{esc(company)}</span>'
        f'<span data-field="location">{esc(location)}</span>'
        f'<span data-field="date">{esc(date)}</span>'
        f'<span data-field="description">{esc(description)}</span>'
        f'<a data-field="link" href="{esc(link)}"></a>'
        f"</div>"
    )


def _wait_until(page_obj: Any, predicate: Any, timeout_ms: float) -> bool:
    """`page_obj.on("response", ...)` ile YAKALANAN bir sonucun gelmesini
    bekler - ag yanitlari ASENKRON oldugu icin `goto()`'nun hemen ardindan
    kontrol etmek yarisa acikti (bkz. modul dokumaninin "M10.2 mimari
    evrimi" notu). `page_obj.wait_for_timeout()` kullanilir (duz
    `time.sleep` DEGIL) - Playwright'in arka plan surucu iletisimi AYRI bir
    thread'de calisir, bu yuzden yanit olaylari bu bekleme SIRASINDA da
    islenmeye devam eder (ampirik olarak dogrulandi)."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if predicate():
            return True
        page_obj.wait_for_timeout(_RESPONSE_POLL_INTERVAL_MS)
    return predicate()


def fetch_search_results_page(
    storage_state: dict[str, Any], location: str, keywords: str, page: int
) -> list[str]:
    """Verilen `storage_state`'i yeni, gorunmez (`headless=True`) bir
    tarayici baglaminda yukleyip, (location, keywords) sorgusu icin
    LinkedIn is arama sonuclarinin `page`.sayfasindaki (0-indexed) ilanlarini
    BIZIM tanimladigimiz, kararli bir sentetik HTML olarak doner (bkz. modul
    dokumaninin "M10.2 mimari evrimi"/"Mimari sinir" notlari).

    Playwright HALA TAM olarak ayni sekilde oturum/kimlik dogrulama/gezinmeyi
    yonetir (`browser.new_context(storage_state=...)`, `page.goto(...)`) -
    DEGISEN TEK SEY, ilan verisinin NEREDEN okundugudur: LinkedIn'in kendi
    istemci tarafi React arayuzunun (bir hydration hatasi nedeniyle DOM'a
    hicbir zaman monte ETMEDIGI - ampirik olarak dogrulandi) render edilmis
    HTML'i YERINE, AYNI gezinmenin dogal bir sonucu olarak Playwright'in
    tarayicisinin ZATEN aldigi ag yaniti govdeleri (`voyagerJobsDashJobCards`,
    `jobPostingDetailDescription`) okunur. Bagimsiz/elle olusturulmus hicbir
    istek YOKTUR.

    Sayfalama SADECE `start` sorgu parametresiyle (0-indexed sayfa *
    `_RESULTS_PER_PAGE`) ifade edilir - bu fonksiyon KENDI BASINA birden
    fazla sayfa gezmez; cagiran (`collection/collector.py`) her sayfayi
    ayri ayri ister ve ne zaman duracagina (bos sonuc veya FR-21 siniri)
    kendisi karar verir.

    Bos liste, bu sorgu icin `page`'de hicbir ilan karti bulunmadigi
    anlamina gelir (sayfalamanin dogal sonu icin kullanilan sinyal) -
    YALNIZCA bir Job Cards yaniti GERCEKTEN geldiginde ve sifir kart
    icerdiginde (LinkedIn'in kendisi bos bir sonuc kumesi dondurdugunde).

    M11.1 duzeltmesi (Roadmap Faz 11, TDD Section 9 "RISK-2"nin nihayet
    ele alinmasi): yanitin HIC gelmemesi (zaman asimi) ARTIK bu bos-liste
    sinyaliyle KARISTIRILMAZ - `JobCardsResponseTimeoutError` firlatilir.
    Bu, `collector.py::_fetch_page_with_retry()`'nin mevcut retry/devre-
    kesici zincirine (M9.4) otomatik olarak akar - `SessionInvalidError`
    DISINDAKI her istisnayi zaten `TransientError`e cevirip yeniden
    dener, bu yuzden `collector.py`'de hicbir degisiklik GEREKMEZ.

    Tarayici, basarili/basarisiz her durumda kapatilir (try/finally).
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(storage_state=storage_state)
            page_obj = context.new_page()

            captured_cards_body: list[str] = []
            captured_descriptions_body: list[str] = []

            def _on_response(response: Any) -> None:
                # `response.text()` bazi yanitlar icin (orn. yonlendirme
                # govdesi yok, baglanti erken kesildi) basarisiz olabilir -
                # bu FATAL degildir: sadece o ESLESMEYI kacirmis oluruz,
                # `_wait_until()`'in zaman asimi (bkz. asagisi) bunu
                # `job_cards`/`descriptions_by_job_id` bos kalarak dogru
                # sekilde ele alir - burada AYRI bir hata yonetimi ICAT
                # EDILMEZ.
                #
                # M10.2 duzeltmesi: bu IKI kontrol KASITLI OLARAK bagimsiz
                # `if`'lerdir (`elif` DEGIL). Onceki `elif` sirasi, bir
                # yanitin URL'si HER IKI isaretle de eslesirse (canli olarak
                # dogrulandi - bkz. `_JOB_CARDS_RESPONSE_URL_MARKER`'in kendi
                # yorumu), ikinci kontrolun ASLA degerlendirilmemesine yol
                # aciyordu. Artik kart-listesi isareti GraphQL yanitlariyla
                # hicbir zaman eslesmeyecek sekilde capa'landigi (yalnizca
                # gercek REST.li yoluyla eslesir) icin bu iki kontrol zaten
                # KARSILIKLI DISLAYICI - bagimsiz `if` kullanimi, gelecekte
                # benzer bir isim CAKISMASI tekrar olusursa bile HER IKI
                # yanitin da (birbirini SESSIZCE ENGELLEMEDEN) dogru
                # sekilde yakalanabilmesini saglar.
                url = response.url
                if _JOB_CARDS_RESPONSE_URL_MARKER in url and not captured_cards_body:
                    with contextlib.suppress(Exception):
                        captured_cards_body.append(response.text())
                if (
                    _JOB_DETAIL_DESCRIPTION_RESPONSE_URL_MARKER in url
                    and not captured_descriptions_body
                ):
                    with contextlib.suppress(Exception):
                        captured_descriptions_body.append(response.text())

            page_obj.on("response", _on_response)

            search_url = (
                f"{SEARCH_URL}?keywords={quote_plus(keywords)}"
                f"&location={quote_plus(location)}"
                f"&start={page * _RESULTS_PER_PAGE}"
            )
            try:
                page_obj.goto(search_url)
            except PlaywrightTimeoutError:
                # M10.2 duzeltmesi (canli bir Bootstrap calistirmasinda
                # kanitlanan bir kusur): `goto()`'nun varsayilan
                # `wait_until="load"` sozu, sayfanin TAM render
                # tamamlanmasini (goruntu/font/vb. dahil) bekler - ama bu
                # fonksiyon ARTIK (M10.2 mimari evrimi) DOM/render
                # tamamlanmasina hic bagimli DEGIL, yalnizca ag yaniti
                # govdesine (`captured_cards_body`) bagimli. Canli kanit:
                # gercek kart yaniti t=7.7s'de basariyla geldi/yakalandi,
                # ama `goto()` KENDI ic "load" beklemesinde t=30.9s'de
                # zaman asimina ugrayip, ZATEN yakalanmis olan veriyi
                # (fonksiyonun butunu iptal edilerek) SESSIZCE cope
                # atiyordu. Duzeltme: bu zaman asimi, YALNIZCA veri HALA
                # yoksa (`not captured_cards_body`) fatal'dir - o durumda
                # davranis DEGISMEDEN korunur (mevcut retry/anomali izleme
                # zinciri - TDD Section 20/RISK-2 - AYNEN calismaya devam
                # eder). Veri ZATEN yakalanmissa, bu zaman asimi YOK
                # sayilir ve fonksiyon asagidaki normal akisina (zaten
                # tatmin olmus `_wait_until` + ayristirma + donus) devam
                # eder - `goto()` yalnizca navigasyonu BASLATAN bir adimdir,
                # fonksiyonun kendi tamamlanma kosulu DEGILDIR.
                if not captured_cards_body:
                    raise

            _wait_until(page_obj, lambda: bool(captured_cards_body), _JOB_CARDS_RESPONSE_TIMEOUT_MS)
            if not captured_cards_body:
                # M11.1: bu, LinkedIn'in gercekten bos sonuc dondurdugu
                # durumdan (asagidaki `if not job_cards:` - orada hala `[]`
                # donulur) KASITLI olarak farklidir - bkz.
                # `JobCardsResponseTimeoutError`'in kendi dokumani.
                raise JobCardsResponseTimeoutError(
                    f"Job Cards ag yaniti {_JOB_CARDS_RESPONSE_TIMEOUT_MS // 1000} "
                    f"saniye icinde hic gelmedi (location={location!r}, "
                    f"keywords={keywords!r}, page={page})."
                )
            job_cards = _parse_job_cards_response(captured_cards_body[0])
            if not job_cards:
                return []

            _wait_until(
                page_obj,
                lambda: bool(captured_descriptions_body),
                _JOB_DESCRIPTIONS_RESPONSE_TIMEOUT_MS,
            )
            descriptions_by_job_id = (
                _parse_job_descriptions_response(captured_descriptions_body[0])
                if captured_descriptions_body
                else {}
            )

            results: list[str] = []
            for card in job_cards:
                job_id = card["job_id"]
                results.append(
                    _build_synthetic_card_html(
                        job_id,
                        card["title"],
                        card["company"],
                        card["location"],
                        card["date"],
                        descriptions_by_job_id.get(job_id, ""),
                        _JOB_VIEW_URL_TEMPLATE.format(job_id=job_id),
                    )
                )
            return results
        finally:
            browser.close()
