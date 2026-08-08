"""LinkedInPort - LinkedIn'e oturum tabanli erisim icin soyut arayuz
(Roadmap M3.1, TDD Section 6/9).

TDD Section 6 modul sorumluluklari tablosu, `adapters.linkedin`'i
`linkedin_port`'un Playwright uygulamasi olarak tanimlar ("oturum
dogrulama/yenileme (FR-1)" sorumluluguyla); Section 9 ise SessionManager'i
"linkedin_port'un bir parcasi" olarak tanimlar. Bu Port, o soyutlamanin
somut kod karsiligidir - Collection Service (M3.3+) ileride bu arayuze
bagimli olacak, Playwright'a degil.

M3.1 KAPSAMI (Roadmap "yalnizca login+kaydetme yolu"): bu asamada Port
yalnizca `ensure_session()` - zaten kalici bir oturum yoksa interaktif
girisi tetikleyip sonucu kalici hale getiren, VARSA hicbir sey yapmayan
(idempotent) TEK bir metod - icerir. Oturumun hala GECERLI olup olmadigini
(sunucu tarafinda suresi dolmus mu) dogrulayan ayri bir `validate()`
metodu KASITLI OLARAK burada YOKTUR - bu, Roadmap M3.2'nin ("Oturum
Dogrulama") acikca ayrilmis kapsamidir; Collection Service'in
kullanacagi arama/sayfalama metodlari (M3.3+) de henuz eklenmemistir.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID


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
