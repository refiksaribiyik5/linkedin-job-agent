# LinkedInBot — Operasyonel Notlar / Olay Kayıtları

Bu dosya, `PRD`/`Roadmap`/`TDD`'nin kapsamadığı **operasyonel olayları**
(production incident'lar, canlı doğrulama sonuçları, çözülmemiş bulgular)
kayıt altına alır. `CLAUDE.md` projenin *o anki* genel durumunu özetler;
bu dosya ise zaman içinde biriken, geriye dönük başvurulacak olay kayıtlarını
tutar — en yeni olay en üstte.

---

## 2026-08-18 — Scheduled Run Tetiklenmedi (Scheduler Incident, ÇÖZÜLMEDİ)

**Durum: Kök neden kesinleşmedi. Önerilen düzeltmeler HENÜZ UYGULANMADI.**

### Olay

`accounts.next_run_at = 2026-08-18 18:15:56.880981 UTC` (`21:15:56 TRT`)
için beklenen scheduled run tetiklenmedi: bu zaman geçtikten sonra ne yeni
bir `run_logs` satırı oluştu, ne `session_status` değişti, ne de
`NEEDS_LOGIN.txt` yazıldı. Manuel müdahale gerekmeden çalışması beklenen
APScheduler `DateTrigger` job'u sessizce kayboldu.

### Kesin, doğrulanmış kanıtlar

- `app-1`, olay anında Commit 2 (`2e531c2`) image'ını çalıştırıyordu,
  `RestartCount=0`, süreç 26+ saattir kesintisiz ayaktaydı.
- Scheduler process/thread'leri canlıydı (`/proc/1/task/`: 2 thread, ikisi
  de `sleeping`, çökmüş/zombi değil).
- `next_run_at` DB'de doğru kaldı, hiç değişmedi (ne uygulama ne biz
  değiştirdik).
- Container/host/Python saatleri tutarlı UTC — **timezone/naive-aware
  sorunu KESİN OLARAK ELENDİ** (offline reproducer'da `DateTrigger`'a
  verilen UTC-aware `run_date`'in mikrosaniyesine kadar değişmeden
  `get_next_fire_time()`'dan döndüğü doğrulandı).
- Mac o sırada uyanıktı ve aktif kullanılıyordu (kullanıcı tarafından
  doğrulandı) — host-seviyesi uyku hipotezi elendi.
- `apscheduler==3.11.3` varsayılanları (canlı image'da doğrulandı):
  `misfire_grace_time=1`, `coalesce=True`, `max_instances=1`.

### Offline reproducer bulguları (`docker compose run --rm` ile izole,
app-1/db-1'e hiç dokunulmadan çalıştırıldı)

- Geçmişte kalan bir `run_date` + varsayılan `misfire_grace_time=1` ile
  test edildiğinde, APScheduler **gerçekten** `EVENT_JOB_MISSED` üretiyor
  ve stderr'e `"Run time of job ... was missed by ..."` uyarısı basıyor —
  bu mekanizma **ampirik olarak doğrulandı**.
- **Ancak gerçek olayda bu uyarı `docker logs`'ta HİÇ görünmedi** (26
  saatlik container ömrü boyunca `docker logs` tamamen boş). Bu proje kod
  tabanında `apscheduler`/root logger için hiçbir suppression yok
  (doğrulandı) — yani bu uyarı, gerçekleşseydi, görünürdü.
- **Sonuç: `misfire_grace_time=1`'in BU SPESİFİK olayın kesin kök nedeni
  olduğu KANITLANMADI** — mekanizma doğru çalıştığı kanıtlandı, ama
  gerçek olayda onun imzası yok. Kök neden **kesinleşmedi**.
- VM/clock pause (Colima/Virtualization.framework) gibi alternatif
  hipotezler **teorik olarak mümkün ama kesin kanıtlanamadı** — canlı
  process'in in-memory job store'unu bozmadan inceleyecek bir araç
  (`py-spy` vb.) bu image'da kurulu değil ve bu incelemede kurulmadı.

### En önemli mimari bulgu

**DB'deki `next_run_at` ile APScheduler'ın in-memory job state'i arasında
hiçbir runtime reconciliation/doğrulama mekanizması yok.** Sistem, süreç
başlangıcında bir kez `add_job()` çağırıp sonraki 2 günlük periyot boyunca
APScheduler'ın kendi iç güvenilirliğine tamamen güveniyor. Buna ek olarak:

- `EVENT_JOB_MISSED` için hiçbir listener yok (`_attach_commit_listeners()`
  yalnızca `EVENT_JOB_EXECUTED`/`EVENT_JOB_ERROR` dinliyor).
- Kaçırılan tek-seferlik bir `DateTrigger`'ın kendiliğinden yeniden
  planlanma mekanizması yok — yalnızca bir sonraki `main.py` süreç
  başlangıcında (`schedule_next_run()` tekrar çağrıldığında) fark edilip
  düzelir.

### Önerilen iyileştirmeler — **HENÜZ UYGULANMADI, yalnızca öneridir**

1. `EVENT_JOB_MISSED` listener eklemek (saf gözlemlenebilirlik kazancı).
2. `misfire_grace_time`'ı açıkça daha büyük bir değere çekmek (varsayılan
   1 saniye aşırı sıkı).
3. DB'yi source-of-truth yapıp periyodik bir reconciliation/heartbeat
   eklemek (`next_run_at` geçmiş VE ilgili `run_logs` yoksa kurtarma) —
   en sağlam, ama en büyük kapsamlı çözüm.

Bu üçü de **tasarım önerisidir**; hiçbiri kodlanmadı, commit edilmedi,
production'a uygulanmadı.

---

## 2026-08-17/18 — Gerçek E2E Doğrulama: Persistent Chromium Profile Mimarisi

**Durum: BAŞARILI, gerçek LinkedIn hesabına karşı canlı olarak doğrulandı.**

Commit 1+2'nin (persistent Chromium profili, `storage_state` cold-replay
mimarisinin yerine) gerçekten çalıştığı, gerçek bir hesaba karşı tek
kontrollü koşuyla kanıtlandı:

- `docker compose run --rm --service-ports app linkedinbot login --account
  <id>` ile Xvfb/noVNC üzerinden interaktif giriş **başarılı**.
- DB `linkedin_sessions.session_status`: `expired` → **`valid`**.
- Persistent profil (`browser-profile/<account_id>/`), login container'ı
  `--rm` ile silindikten SONRA da host'ta kaldı; **ayrı, bağımsız bir
  sonraki container** (hem bir doğrulama container'ı hem asıl manual run
  container'ı) **aynı** profili gördü — bind-mount kalıcılığı canlı
  kanıtlandı.
- `SessionManager.validate()` başarılı — LinkedIn `/feed/`'i kabul etti.
- Collection: **194 job card toplandı**, **167 yeni**, **28 filtrelendi**,
  **0 kapandı**.
- `RunLog.status = Partial`, `partial_reason`: `max_jobs_per_run=200`
  sınırına ulaşıldığı için toplama kesildi (bu bir hata DEĞİL, kasıtlı
  FR-21 limiti).
- Rapor dosyası gerçek AI Match Score/Company Quality Score/rasyonel
  içerikle oluştu — pipeline'ın Collection'dan Report Compilation'a kadar
  **tamamı** çalıştı.

**Not:** Bu E2E run'ın kendisi (RunLog satırı, rapor dosyası) production
DB'de ve gitignore'lu `reports/` dizininde yaşıyor — kasıtlı olarak Git'e
**dahil edilmedi** (PRD/TDD Section 24/27'nin "runtime çıktıları asla
commit edilmez" kararıyla tutarlı).
