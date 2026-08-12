"""SchedulerPort - hesap basina otomatik zamanlama icin soyut arayuz
(Roadmap M9.6, TDD Section 12/PRD FR-12/NFR-14).

TDD Section 12 "Zamanlama Mimarisi", Port'un iki islemini acikca sayar:
"`schedule_next_run(account_id, interval, jitter_window)`, `cancel(account_id)`
gibi islemleri soyutlar." Somut implementasyonu (`APSchedulerAdapter`,
M9.6, `adapters/scheduling/apscheduler_adapter.py`) surec-ici (in-process)
APScheduler kullanir; bu Port, o teknoloji secimine (Hexagonal Mimari,
TDD Section 1 Karar 2) hicbir sekilde bagimli degildir.

**Bu Port'un kapsami NE DEGILDIR (kullanici talimatiyla acikca sinirlanan
sahiplik siniri):** `main.py`'nin surec giris noktasi/dependency-wiring
sorumlulugu (TDD Section 9 "Surec modeli," Section 5 dosya agacinda ayrica
listelenir, M9.6'nin "Oluşturulacak Dosyalar" listesinde YER ALMAZ) ve
`cli.py`'nin manuel tetikleme komutu (Roadmap M9.7, "CLI Genişletmesi")
bu Port'un DISINDADIR. `schedule_next_run()` bir Run'i DOGRUDAN baslatmaz -
yalnizca, cagiranin (constructor'da enjekte ettigi) bir geri-cagirmayi
(callback) dogru zamanda tetikler; o geri-cagirmanin GERCEK isi (orn.
`orchestrator.run()`'u cagirmak icin `OrchestratorDependencies`'i
somutlastirmak) `main.py`'nin (henuz insa edilmemis) sorumlulugudur.

**RunLock (M9.1) neden bu Port'ta GORUNMEZ:** TDD Section 12 - "Hem
otomatik hem manuel tetikleme AYNI kilidi kontrol eder" - bu, `RunLock`'un
`orchestrator.run()` ICINDE (M9.3, degistirilmemis) zaten uygulandigi
icin DOGAL olarak saglanir; hem zamanlanmis hem manuel tetiklemeler
ayni `orchestrator.run()` cagrisina ULASTIGI surece, cakisma onleme
otomatik olarak GECERLIDIR - Scheduler'in kendisinin RunLock'a AYRICA
dokunmasi gerekmez (bu yuzden Roadmap'in "Bağımlılıklar: M9.3, M9.1"
satiri, M9.6'nin RunLock'u DOGRUDAN import etmesi anlamina GELMEZ -
kavramsal/gecisli bir bagimliliktir).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from uuid import UUID


class SchedulerPort(ABC):
    """Hesap basina otomatik zamanlama icin temel islemler (Roadmap M9.6)."""

    @abstractmethod
    def schedule_next_run(
        self, account_id: UUID, interval: timedelta, jitter_window: timedelta
    ) -> datetime:
        """Bu hesap icin bir sonraki otomatik tetiklenmeyi ayarlar ve
        `accounts.next_run_at`'i (TDD v1.1 Fix 5) kalici hale getirir.

        Hesabin ZATEN gelecekte bir `next_run_at`'i varsa (surec yeniden
        baslatma sonrasi kurtarma senaryosu - TDD Section 12 "Kalıcılık")
        bu deger OLDUGU GIBI onurlandirilir, yeniden hesaplanmaz. Yoksa
        (hic zamanlanmamis) VEYA GECMISTE kaldiysa (misfire sonrasi veya
        uzun bir kesinti sonrasi yeniden baslatma), `simdiki zaman +
        interval ± jitter_window` ile TAZE bir deger hesaplanir - bu,
        APScheduler'in kendi devre-disi-birakilmamis varsayilan misfire
        davranisiyla (bkz. APSchedulerAdapter modul dokumani) AYNI
        "kacan bir olusumu atla, bir sonrakine gec" semantigidir, YENI
        bir "yakalama" (catch-up) politikasi ICAT ETMEZ.

        Doner: cozumlenen `next_run_at` degeri.
        """

    @abstractmethod
    def cancel(self, account_id: UUID) -> None:
        """Bu hesap icin bekleyen HERHANGI bir zamanlanmis tetiklemeyi
        iptal eder ve `accounts.next_run_at`'i temizler (None yapar).
        Zaten hicbir sey zamanlanmamissa sessiz bir no-op'tur (Account
        Repository'nin `get_by_id()`'sinin "sessiz varsayilan uretmez,
        None doner" ilkesiyle AYNI ruhta - ama burada "bulunamadi"
        HATA degil, GECERLI bir baslangic durumudur)."""
