"""LinkedInPort - LinkedIn'e oturum tabanli erisim icin soyut arayuz
(Roadmap M3.1, TDD Section 6/9).

TDD Section 6 modul sorumluluklari tablosu, `adapters.linkedin`'i
`linkedin_port`'un Playwright uygulamasi olarak tanimlar ("oturum
dogrulama/yenileme (FR-1)" sorumluluguyla); Section 9 ise SessionManager'i
"linkedin_port'un bir parcasi" olarak tanimlar. Bu Port, o soyutlamanin
somut kod karsiligidir - Collection Service (M3.3+) ileride bu arayuze
bagimli olacak, Playwright'a degil.

M3.1 KAPSAMI (Roadmap "yalnizca login+kaydetme yolu"): o asamada Port
yalnizca `ensure_session()` - zaten kalici bir oturum yoksa interaktif
girisi tetikleyip sonucu kalici hale getiren, VARSA hicbir sey yapmayan
(idempotent) TEK bir metod - icerdi. Collection Service'in kullanacagi
arama/sayfalama metodlari (M3.3+) henuz eklenmemistir.

M3.2 KAPSAMI (Roadmap "Oturum Dogrulama", FR-1): Port'a `validate()`
eklenir - kalici bir oturumun HALA gecerli olup olmadigini (sunucu
tarafinda suresi dolmus mu) canli olarak kontrol eder. Gecersiz bir
oturum `SessionInvalidError` firlatir; TDD Section 20'nin hata
taksonomisinde bu bir `PermanentError` olarak siniflandirilir (retry
edilmez) - ama o merkezi taksonomi sinifi (`PermanentError` temel
sinifi) henuz insa edilmemistir (Roadmap M9.3, "Hata Siniflandirma +
Retry"); bu yuzden `SessionInvalidError` simdilik bagimsiz, kendi
basina bir exception olarak tanimlanir, var olmayan bir taksonomi
sinifindan miras almaz.

M3.3 KAPSAMI (Roadmap "Arama & Sayfalama", FR-21): Port'a
`search_jobs_page()` eklenir - verilen bir (location, keywords, page)
sorgusu icin TEK bir sayfalik ham ilan karti HTML'lerini doner. Bu
metodun Port'a (adapters.linkedin'e degil, dogrudan Playwright'a da
degil) eklenmesi KASITLI bir mimari karardir (proje talimatiyla acikca
onaylandi): TDD Section 6'nin modul sorumluluklari tablosu, `collection`
modulunun BAGIMLI OLDUGU Port'u acikca `linkedin_port` olarak listeler -
`collection/collector.py` (Roadmap M3.3) bu yuzden Playwright'i HICBIR
ZAMAN dogrudan import etmez, yalnizca bu Port'a bagimlidir. Sayfalama
MANTIGI (kac sayfa gidilecegi, FR-21'in ust siniri, `collection_capped`
bayragi) BURADA DEGIL, `collection/collector.py`'de yasar - bu metod
yalnizca TEK bir sayfa getirir, ne zaman durulacagina karar vermez.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID


class SessionInvalidError(Exception):
    """Verilen hesap icin kalici bir LinkedIn oturumu yoktur veya artik
    LinkedIn tarafindan kabul edilmiyor (FR-1). `LinkedInPort.validate()`
    tarafindan firlatilir; genel bir crash degil, cagiranin (ileride Run
    Orchestrator, M9) ayirt edip Run'i "Failed" olarak isaretleyebilecegi
    tanimli bir hata turudur (bkz. TDD Section 9/20).
    """


class LinkedInPort(ABC):
    """LinkedIn'e oturum tabanli erisimin soyut arayuzu."""

    @abstractmethod
    def ensure_session(self, account_id: UUID) -> None:
        """Verilen hesap icin kalici bir oturum (storage_state) yoksa,
        kullanicinin tarayicida interaktif olarak giris yapmasini bekler
        ve sonucu Secrets Provider uzerinden kalici hale getirir. Zaten
        kalici bir oturum VARSA hicbir sey yapmaz (idempotent) - bu, ayni
        surecin tekrar tekrar calistirilmasinin (orn. bir sonraki
        zamanlanmis calistirmada) yeniden interaktif giris istememesini
        garanti eder (Roadmap M3.1 "Beklenen Sonuc").
        """

    @abstractmethod
    def validate(self, account_id: UUID) -> None:
        """Verilen hesap icin kalici oturumun HALA gecerli olup olmadigini
        canli olarak (LinkedIn'e karsi) kontrol eder. Gecersiz, suresi
        dolmus veya hic var olmayan bir oturum sessizce yutulmaz -
        `SessionInvalidError` firlatilir (FR-1). Gecerliyse hicbir sey
        firlatmadan doner.
        """

    @abstractmethod
    def search_jobs_page(
        self, account_id: UUID, location: str, keywords: str, page: int
    ) -> list[str]:
        """Verilen hesabin kalici oturumunu kullanarak, (location, keywords)
        sorgusu icin LinkedIn is arama sonuclarinin `page`.sayfasindaki
        (0-indexed) ham ilan karti HTML'lerini doner. Bos liste, o sorgu
        icin baska sayfa olmadigi (sayfalamanin dogal sonu) anlamina
        gelir. Kalici bir oturum yoksa/gecersizse `SessionInvalidError`
        firlatilir - Collection (bu metod), pipeline'da Session
        Validation'dan (M3.2) SONRA calisir (PRD Workflow adim 2->3).
        """
