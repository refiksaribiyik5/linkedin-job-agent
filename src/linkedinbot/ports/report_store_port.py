"""ReportStorePort - uretilen Markdown rapor iceriginin kalici depolamaya
yazilmasi icin soyut arayuz (Roadmap M8.3, FR-17, TDD Section 18 adim 3).

Bu Port, `ReportRepositoryPort`'tan (M1.3, degistirilmemis) BILEREK
AYRIDIR: `ReportRepositoryPort` `reports` DB satirinin (metadata) kalici
hale gelmesinden sorumludur, bu Port ise raporun KENDI Markdown
ICERIGININ (dosya) kalici hale gelmesinden sorumludur - TDD Section 18'in
adim 3'u (ReportStore) ile adim 4'u (reports tablosu satiri) acikca IKI
AYRI islem olarak tanimlanir.

FR-17'nin "uzerine yazilmadan kalici hale gelir" gereksinimi, Port'un
KENDI sozlesmesinin bir parcasidir (yalnizca V1 adaptorunun rastgele bir
tercihi degil) - `ReportRepositoryPort`'un kendi modul dokumaninin ayni
gerekce ile KASITLI OLARAK bir `update()` metodu TANIMLAMAMASIYLA (mumkun
olmayan bir islemi arayuzde hic tanimlamamak, yanlislikla cagrilmaktan
daha guvenlidir) AYNI ilkeyi izler: her `save()` cagirisi ya YENI bir
konuma yazar ya da acikca basarisiz olur, hicbir zaman sessizce mevcut
bir raporun uzerine yazmaz.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from uuid import UUID


class ReportStorePort(ABC):
    """Rapor Markdown iceriginin kalici depolamaya yazilmasi (Roadmap M8.3)."""

    @abstractmethod
    def save(self, account_id: UUID, report_id: UUID, generated_at: datetime, content: str) -> Path:
        """Markdown icerigini kalici olarak saklar ve kullanilan yolu doner.

        FR-17 geregi mevcut bir raporun uzerine ASLA yazilmaz - hedef konum
        zaten doluysa uygulama acikca basarisiz olmalidir (sessizce
        uzerine yazmak veya sessizce atlamak yerine).
        """
