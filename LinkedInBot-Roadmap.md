# LinkedInBot — Implementation Roadmap

### Document Control

| Alan | Değer |
|---|---|
| Doküman Türü | Implementation Roadmap (Living Document) |
| Proje Kod Adı | LinkedInBot |
| Versiyon | 1.0 |
| Durum | Draft — Kodlamaya Başlamadan Önce |
| Kaynak PRD | LinkedInBot-PRD.md, **v1.3** |
| Kaynak TDD | LinkedInBot-TDD.md, **v1.1** |
| Son Güncelleme | 2026-08-07 |
| Kapsam | V1 (MVP) — kod içermez, yalnızca sıralı milestone planı |

---

## 0. Amaç ve Kullanım Notu

Bu belge, TDD'de tanımlanan mimariyi **küçük, bağımsız olarak uygulanabilir, test edilebilir ve gözden geçirilebilir** milestone'lara böler. Her milestone tek başına bir oturumda (genellikle birkaç saat) tamamlanabilecek büyüklüktedir; hiçbir milestone bir öncekini tamamlamadan başlatılmamalıdır (bağımlılıklar açıkça belirtilmiştir).

**Sıralama mantığı:** Fazlar, TDD'nin veri akışı sırasını (Section 8) takip eder — önce temel (domain/DB/config), sonra dış dünyaya bağlanan adaptörler, sonra pipeline aşamaları (Collection → Filtering → Scoring → Reporting), en son orkestrasyon/zamanlama/paketleme. Bu sıra, her milestone'un bir öncekinin üzerine gerçek, çalışan bir temel kurmasını sağlar — hiçbir aşama, henüz var olmayan bir bileşene bağımlı kalmaz.

**Süre tahminleri** tek bir geliştiricinin Claude Code ile çalıştığı varsayımıyla verilmiştir: şema/domain/config gibi belirlenimci, iyi tanımlanmış işler için düşük uçlar gerçekçidir (Claude Code boilerplate'i hızlı üretir); LinkedIn scraping ve LLM prompt kalibrasyonu gibi gerçek dünya belirsizliği içeren işler için yüksek uçlar daha gerçekçidir (seçici/CSS kırılganlığı, prompt iterasyonu insan yargısı gerektirir, otomatikleştirilemez).

**Her milestone'un doğrulaması bağımsızdır** — bir sonraki milestone'a geçmeden önce o milestone'un "Tamamlanma Doğrulaması" adımı çalıştırılmalı ve geçmelidir.

---

## Hızlı Referans Tablosu

| Faz | Milestone Sayısı | Odak | Tahmini Süre Aralığı |
|---|---|---|---|
| Faz 0 — Proje İskeleti | 2 | Tooling, Docker | 2–4 saat |
| Faz 1 — Domain & Veri Katmanı | 4 | Pydantic modeller, DB şema, repository, seed | 13–20 saat |
| Faz 2 — Konfigürasyon & Secrets | 4 | Config doğrulama/yükleme, secrets, CLI iskeleti | 11–17 saat |
| Faz 3 — LinkedIn Toplama | 5 | Playwright oturum, arama, çıkarım, rate limit | 17–30 saat |
| Faz 4 — Normalizasyon & Geçmiş | 2 | Content hash, New/Seen/Updated/Closed | 7–10 saat |
| Faz 5 — LLM Altyapısı | 3 | Provider adaptörü, prompt registry, Gateway | 11–18 saat |
| Faz 6 — Filtreleme | 5 | Blacklist, Location, Experience, Department, zincir | 13–20 saat |
| Faz 7 — Skorlama | 3 | Company Quality Score, AI Match Score, Borderline | 13–19 saat |
| Faz 8 — Sıralama & Raporlama | 3 | Ranking, rapor şablonu, kalıcı depolama | 8–12 saat |
| Faz 9 — Orkestrasyon & Zamanlama | 7 | RunLock, Company Score Repository, Orchestrator, hata/retry, log, scheduler, CLI | 23–35 saat |
| Faz 10 — Paketleme & İlk Çalıştırma | 2 | Docker Compose tamamlama, gerçek bootstrap run | 5–9 saat |
| **Toplam** | **40** | | **≈123–194 saat** (~3–5 hafta tam zamanlı, ~6–9 hafta yarı zamanlı) |

*En büyük belirsizlik kaynakları: Faz 3 (LinkedIn'in gerçek DOM yapısı/seçicileri) ve Faz 5–7 (prompt kalitesi/grounding iterasyonu). Diğer fazlar büyük ölçüde belirlenimcidir ve tahminlerin alt ucuna yakın seyretmesi beklenir.*

---

## Faz 0 — Proje İskeleti

### M0.1 — Repository ve Tooling Bootstrap
- **Amaç:** Python paket yapısını, bağımlılık yönetimini ve kod kalitesi araçlarını kurmak; TDD Section 5'teki klasör iskeletini oluşturmak.
- **Oluşturulacak Dosyalar:** `pyproject.toml`, `.gitignore`, `.env.example`, `src/linkedinbot/__init__.py`, TDD Section 5'teki boş klasör iskeleti (`domain/`, `ports/`, `adapters/`, `collection/`, `filtering/`, `scoring/`, `ranking/`, `reporting/`, `run/`, `config/`, `db/`, `logging/`, `tests/unit/`, `tests/integration/`).
- **Bileşenler:** Yok (salt tooling).
- **Bağımlılıklar:** Yok.
- **Beklenen Sonuç:** `pip install -e .` başarıyla kurulur; linter/formatter (örn. ruff) boş iskelet üzerinde temiz geçer.
- **Tamamlanma Doğrulaması:** `python -c "import linkedinbot"` hatasız çalışır; `ruff check .` sıfır hata döner.
- **Tahmini Süre:** 1–2 saat.

### M0.2 — Yerel Geliştirme Altyapısı (Docker)
- **Amaç:** PostgreSQL'i konteynerde ayağa kaldırmak (uygulama konteyneri henüz yok — bu daha sonra Faz 10'da tamamlanır).
- **Oluşturulacak Dosyalar:** `docker-compose.yml` (yalnızca `db` servisi), `Dockerfile` (taslak, henüz kullanılmıyor).
- **Bileşenler:** PostgreSQL 16 konteyneri.
- **Bağımlılıklar:** M0.1.
- **Beklenen Sonuç:** `docker compose up db` ile boş bir Postgres örneği host makineden erişilebilir durumda çalışır.
- **Tamamlanma Doğrulaması:** `psql` veya eşdeğer bir istemciyle bağlantı kurulur, boş bir veritabanı görülür.
- **Tahmini Süre:** 1–2 saat.

---

## Faz 1 — Domain & Veri Katmanı

### M1.1 — Domain Modelleri (Pydantic)
- **Amaç:** PRD Section 15'teki kavramsal varlıkları (User Profile, Job Posting, Company Profile, Evaluated Job, Report, Run Log) ve TDD'nin `AccountContext`'ini tip-güvenli Pydantic modelleri olarak tanımlamak.
- **Oluşturulacak Dosyalar:** `domain/job_posting.py`, `domain/company_profile.py`, `domain/evaluated_job.py`, `domain/user_profile.py`, `domain/report.py`, `domain/run_log.py`, `domain/account_context.py`.
- **Bileşenler:** Domain katmanı (Section 3'teki "Domain/Core").
- **Bağımlılıklar:** M0.1.
- **Beklenen Sonuç:** Her varlık, PRD 15.x'teki alan listesiyle birebir örtüşen, doğrulanabilir bir model olarak var olur; hiçbir model dış kütüphaneye (DB, HTTP) bağımlı değildir.
- **Tamamlanma Doğrulaması:** Birim testleri her modeli geçerli veriyle örnekler ve geçersiz veriyle (örn. skor aralığı dışı bir AI Match Score) `ValidationError` fırlatıldığını doğrular.
- **Tahmini Süre:** 3–5 saat.

### M1.2 — Veritabanı Şeması v1
- **Amaç:** TDD Section 15'teki (v1.1 düzeltmeleri dahil) tüm tabloları somutlaştırmak: `accounts` (+ `next_run_at`), `user_profiles`, `account_config_profiles` (+ `target_criteria`), `linkedin_sessions`, `evaluated_jobs`, `reports`, `run_logs`, `run_locks` (+ `lock_expires_at`), `companies`, `company_scores` (+ `rubric_version`), `job_postings`.
- **Oluşturulacak Dosyalar:** `db/engine.py`, `db/models.py`, `alembic.ini`, `migrations/versions/0001_initial_schema.py`.
- **Bileşenler:** Veritabanı katmanı (SQLAlchemy + Alembic).
- **Bağımlılıklar:** M0.2, M1.1.
- **Beklenen Sonuç:** `alembic upgrade head` çalıştırıldığında TDD v1.1'deki her tablo ve sütun (5 mimari düzeltme dahil) eksiksiz oluşur.
- **Tamamlanma Doğrulaması:** Şema, TDD Section 15 tablolarıyla satır satır karşılaştırılır; her tabloya bir örnek satır eklenip okunarak temel bütünlük doğrulanır.
- **Tahmini Süre:** 4–6 saat.

### M1.3 — Repository Katmanı
- **Amaç:** Her domain varlığı için CRUD/sorgu arayüzlerini oluşturmak; Account-Scoped tablolarda `account_id` parametresi zorunlu kılınır (TDD Section 14 kuralı).
- **Oluşturulacak Dosyalar:** `db/repositories/account_repository.py`, `job_repository.py`, `company_repository.py`, `evaluated_job_repository.py`, `report_repository.py`, `run_log_repository.py`.
- **Bileşenler:** Repository katmanı.
- **Bağımlılıklar:** M1.2.
- **Beklenen Sonuç:** Her varlık için temel create/read/update işlemleri çalışır durumdadır. `EvaluatedJobRepositoryPort`, ayrıca bir hesabın tüm değerlendirilmiş ilanlarını döndüren tek bir toplu okuma metodu (`list_by_account(account_id) -> list[EvaluatedJob]`) sağlar — M9.3'ün tasarım incelemesinde bulunan bir boşluğun (Gap D) düzeltmesidir: `history/diff_engine.py`'nin (M4.2, değiştirilmemiş) Closed-ilan tespiti (FR-10, Must-have) hesabın önceden bilinen tüm ilanlarını gerektirir; tek-kayıt sorgulayan `get_by_account_and_job` bunu karşılayamaz. Metot herhangi bir durum filtrelemesi yapmaz (ham liste döner) — filtreleme mantığı zaten `diff_job_postings()`'in kendisindedir.
- **Tamamlanma Doğrulaması:** Birim testleri (test DB'sine karşı) her repository için CRUD akışını doğrular; Account-Scoped bir repository metodunun `account_id` olmadan çağrılamayacağı (imza seviyesinde) doğrulanır. `list_by_account`'ın bir hesabın birden fazla kaydını doğru döndürdüğü ve başka bir hesabın kayıtlarını hiçbir şekilde sızdırmadığı ayrıca doğrulanır.
- **Tahmini Süre:** 4–6 saat.

### M1.4 — Bootstrap / Seed Script'i
- **Amaç:** V1'in tek hesabını ve başlangıç konfigürasyon profilini oluşturmak.
- **Oluşturulacak Dosyalar:** `config/system.defaults.yaml`, `config/accounts/default.account.yaml`, seed script (`cli.py`'nin ilk taslağı veya ayrı bir `scripts/seed.py`).
- **Bileşenler:** Config Service (ilk hali), Account Service.
- **Bağımlılıklar:** M1.3.
- **Beklenen Sonuç:** Boş bir veritabanına karşı seed çalıştırıldığında bir `accounts` satırı, bir `user_profiles` satırı ve `config_version=1, is_active=true` olan bir `account_config_profiles` satırı oluşur. `system.defaults.yaml`'ın `thresholds` bölümü, ayrıca `department_confidence_tolerance` için bir varsayılan değer taşır (bkz. M2.1 düzeltmesi, Gap B) — somut sayısal değer, mimari belgede sabitlenmez; M9.3'ün implementasyon aşamasında belirlenir.
- **Tamamlanma Doğrulaması:** Seed sonrası DB sorgulanır; oluşan hesap kimliğiyle (henüz taslak) bir `AccountContext` kurulabildiği doğrulanır.
- **Tahmini Süre:** 2–3 saat.

---

## Faz 2 — Konfigürasyon & Secrets

### M2.1 — Config Şeması ve Doğrulama
- **Amaç:** FR-13/EDGE-15'in doğrulama kurallarını (ağırlık toplamı %100, eşik aralıkları, referans bütünlüğü) kod haline getirmek.
- **Oluşturulacak Dosyalar:** `config/schema.py`, `config/validator.py`.
- **Bileşenler:** Config Service.
- **Bağımlılıklar:** M1.1.
- **Beklenen Sonuç:** Geçerli bir config kabul edilir; toplamı %100 olmayan ağırlıklar veya tanımsız bir departman referansı reddedilir ve anlaşılır bir hata mesajı üretir. `Thresholds`, ayrıca yapılandırılabilir bir `department_confidence_tolerance: float` (0–1 aralığında) alanını taşır — M9.3'ün tasarım incelemesinde bulunan bir boşluğun (Gap B) düzeltmesidir: `filtering/pipeline.py`'nin (M6.5, değiştirilmemiş) Department borderline mantığı bu değeri zorunlu bir parametre olarak alır, ancak `borderline_band_width` (yalnızca 0–100 puanlık AI Match Score ölçeğinde tanımlı) M6.5'in kendi onaylanmış kararıyla buraya doğrudan uygulanamaz.
- **Tamamlanma Doğrulaması:** Birim testleri en az bir geçerli ve üç geçersiz (ağırlık toplamı hatalı, eşik aralık dışı, tanımsız referans) config ile doğrulayıcıyı çalıştırır. `department_confidence_tolerance` alanının 0–1 aralığı dışında bir değerle reddedildiği ayrıca doğrulanır.
- **Tahmini Süre:** 3–5 saat.

### M2.2 — Config Loader (Öncelik Zinciri + AccountContext)
- **Amaç:** TDD Section 23'teki öncelik zincirini (varsayılanlar → sistem defaults → hesap profili → env) uygulamak ve çalıştırma başına "dondurulmuş" bir `AccountContext` üretmek.
- **Oluşturulacak Dosyalar:** `config/loader.py`.
- **Bileşenler:** Config Service.
- **Bağımlılıklar:** M2.1, M1.3, M1.4.
- **Beklenen Sonuç:** `load_account_context(account_id)` çağrısı, doğrulanmış, versiyonlanmış, tam çözümlenmiş bir konfigürasyon döndürür.
- **Tamamlanma Doğrulaması:** Bir config yüklenip context oluşturulduktan sonra DB'deki config değiştirilir; aynı context'in hâlâ eski (donmuş) değerleri taşıdığı doğrulanır.
- **Tahmini Süre:** 3–4 saat.

### M2.3 — Secrets Provider
- **Amaç:** LLM API anahtarı ve (ileride) LinkedIn oturum verisi için şifreli, arayüz üzerinden erişilen bir depo kurmak.
- **Oluşturulacak Dosyalar:** `ports/secrets_provider_port.py`, `adapters/secrets/local_keyring_adapter.py`.
- **Bileşenler:** Secrets Provider.
- **Bağımlılıklar:** M0.1.
- **Beklenen Sonuç:** Bir secret yazılıp okunabilir; disk üzerindeki dosya düz metin içermez.
- **Tamamlanma Doğrulaması:** Birim testi round-trip yapar; disk dosyası doğrudan açılarak (hex/binary dump) düz metin secret'ın görünmediği manuel olarak teyit edilir.
- **Tahmini Süre:** 3–5 saat.

### M2.4 — CLI İskeleti + `config validate`
- **Amaç:** İlk gerçek CLI komutunu bağlamak.
- **Oluşturulacak Dosyalar:** `cli.py`.
- **Bileşenler:** CLI adaptörü.
- **Bağımlılıklar:** M2.1, M2.2.
- **Beklenen Sonuç:** `linkedinbot config validate` komutu, geçerli/geçersiz config için doğru çıkış kodu ve mesajla sonuçlanır.
- **Tamamlanma Doğrulaması:** Bilinen iyi ve kötü config dosyalarıyla manuel çalıştırma.
- **Tahmini Süre:** 2–3 saat.

---

## Faz 3 — LinkedIn Toplama (Collection)

### M3.1 — LinkedIn Port + Oturum Açma Akışı
- **Amaç:** Playwright ile tek seferlik interaktif girişi gerçekleştirip oturumu kalıcı hale getirmek; parolanın hiçbir zaman diske yazılmadığını garanti etmek (TDD Section 24 kararı).
- **Oluşturulacak Dosyalar:** `ports/linkedin_port.py`, `adapters/linkedin/playwright_client.py`, `adapters/linkedin/session_manager.py` (yalnızca login+kaydetme yolu).
- **Bileşenler:** LinkedIn Port/Adapter, Secrets Provider.
- **Bağımlılıklar:** M2.3.
- **Beklenen Sonuç:** Bir kez interaktif giriş yapıldıktan sonra oturum `storage_state` olarak Secrets Provider üzerinden saklanır; süreç yeniden başlatıldığında kimlik bilgisi tekrar istenmez.
- **Tamamlanma Doğrulaması:** Manuel — giriş yap, süreci kapat, tekrar başlat, oturumun yeniden kullanıldığını (yeniden login istenmediğini) doğrula.
- **Tahmini Süre:** 4–8 saat (gerçek giriş akışında beklenmedik sürtünme olasıdır).

### M3.2 — Oturum Doğrulama (FR-1)
- **Amaç:** Geçersiz/süresi dolmuş oturumu sessizce yutmadan tespit etmek.
- **Oluşturulacak Dosyalar:** `session_manager.py`'ye `validate()` yolu eklenir (yeni dosya yok).
- **Bileşenler:** LinkedIn Adapter.
- **Bağımlılıklar:** M3.1.
- **Beklenen Sonuç:** Geçersiz oturum `SessionInvalidError` fırlatır; genel bir crash değil, tanımlı bir hata türüdür.
- **Tamamlanma Doğrulaması:** Kayıtlı oturumu manuel olarak geçersizleştirip (örn. çerezi silerek) doğrulamayı tekrar çalıştır; doğru hata türünün fırlatıldığını doğrula.
- **Tahmini Süre:** 2–4 saat.

### M3.3 — Arama & Sayfalama
- **Amaç:** Config'teki lokasyon/anahtar kelimelerle arama yapmak, FR-21'in üst sınırına kadar sayfalamak.
- **Oluşturulacak Dosyalar:** `collection/collector.py` (SearchClient + PaginationController mantığı).
- **Bileşenler:** Collection Service.
- **Bağımlılıklar:** M3.2, M2.2.
- **Beklenen Sonuç:** Geçerli bir oturum ve config ile, sınırlı sayıda ham arama sonucu döner; sınıra ulaşılırsa `collection_capped=true` işaretlenir.
- **Tamamlanma Doğrulaması:** Gerçek hesapla, `max_jobs_per_run=5` gibi düşük bir sınırla çalıştırılır; tam olarak ≤5 sonuç ve doğru cap bayrağı doğrulanır.
- **Tahmini Süre:** 6–10 saat (LinkedIn'in DOM/seçici kırılganlığı en büyük risk).

### M3.4 — Alan Çıkarımı ve Kısmi Hata Toleransı
- **Amaç:** Her ilan kartından FR-2'nin minimum alan setini çıkarmak; bozuk bir kaydın çalıştırmayı durdurmamasını sağlamak.
- **Oluşturulacak Dosyalar:** `collection/collector.py` içine RecordExtractor eklenir.
- **Bileşenler:** Collection Service.
- **Bağımlılıklar:** M3.3.
- **Beklenen Sonuç:** Bozuk bir kart `PartialRecordError` olarak yakalanıp atlanır, akış devam eder.
- **Tamamlanma Doğrulaması:** Kaydedilmiş bir HTML fixture'ı içine kasıtlı olarak bozuk bir kart eklenir; testte diğer tüm kayıtların işlendiği ve bozuk olanın loglanıp atlandığı doğrulanır.
- **Tahmini Süre:** 3–5 saat.

### M3.5 — Rate Limiting + Jitter
- **Amaç:** İstekler arası gecikme ve zamanlama sapmasını uygulamak (TDD Section 22).
- **Oluşturulacak Dosyalar:** `collection/collector.py` içine RateLimiter eklenir (veya ayrı bir yardımcı modül).
- **Bileşenler:** Collection Service.
- **Bağımlılıklar:** M3.3.
- **Beklenen Sonuç:** İstekler arası gecikme konfigüre edilebilir aralıkta gerçekleşir; paralel oturum yoktur.
- **Tamamlanma Doğrulaması:** Test çalıştırmasında istekler arası geçen süre ölçülür ve konfigüre edilen aralıkla uyumlu olduğu doğrulanır.
- **Tahmini Süre:** 2–3 saat.

---

## Faz 4 — Normalizasyon & Geçmiş

### M4.1 — Normalizasyon + Content Hash
- **Amaç:** Ham veriyi `JobPosting` domain modeline dönüştürmek; `content_hash`'i yalnızca FR-14 kapsamındaki alanlardan (Title, Experience Level, Location, Workplace Type, Description) hesaplamak (TDD v1.1 Fix 4).
- **Oluşturulacak Dosyalar:** `normalization/normalizer.py`.
- **Bileşenler:** Normalization Service.
- **Bağımlılıklar:** M3.4, M1.1.
- **Beklenen Sonuç:** Değişmemiş bir ilanın iki farklı taramasında (oynak alanlar farklı olsa da) `content_hash` aynı kalır.
- **Tamamlanma Doğrulaması:** Birim testi — yalnızca görüntülenme sayısı gibi oynak bir alanı farklı olan iki fixture aynı hash'i üretir; Description'ı farklı bir üçüncü fixture farklı hash üretir.
- **Tahmini Süre:** 3–4 saat.

### M4.2 — Geçmişle Çapraz Kontrol (Diff Engine)
- **Amaç:** Her ilanı New/Seen/Updated/Closed durumlarından birine atamak.
- **Oluşturulacak Dosyalar:** `history/diff_engine.py`, `history/content_hasher.py`.
- **Bileşenler:** History/Diff Engine.
- **Bağımlılıklar:** M4.1, M1.3.
- **Beklenen Sonuç:** FR-8/FR-9/FR-10/FR-14 durumları iki ardışık simüle edilmiş çalıştırma boyunca doğru atanır.
- **Tamamlanma Doğrulaması:** Kontrollü bir fixture setiyle (bir değişmemiş, bir değişmiş, bir kaybolmuş, bir yeni ilan) diff engine iki kez çalıştırılır; sırasıyla Seen/Updated/Closed/New doğrulanır.
- **Tahmini Süre:** 4–6 saat.

---

## Faz 5 — LLM Altyapısı

### M5.1 — LLM Provider Port + Anthropic Adapter (Temel)
- **Amaç:** Yapılandırılmış çıktı destekli temel bir LLM çağrı sarmalayıcısı kurmak (henüz kademelendirme/cache yok).
- **Oluşturulacak Dosyalar:** `ports/llm_provider_port.py`, `adapters/llm/anthropic_adapter.py`.
- **Bileşenler:** LLM Provider Adapter.
- **Bağımlılıklar:** M2.3 (API anahtarı için).
- **Beklenen Sonuç:** Tek bir test prompt'u gerçek bir çağrıyla gidip yapılandırılmış bir yanıt olarak döner.
- **Tamamlanma Doğrulaması:** Entegrasyon testi bir gerçek çağrı yapar, yanıtın beklenen şemaya uyduğunu doğrular.
- **Tahmini Süre:** 3–5 saat.

### M5.2 — Prompt Registry + Şablonlar
- **Amaç:** Dört prompt şablonunu (department matching, experience inference, company scoring, AI match rationale) versiyonlanmış dosyalar olarak yönetmek.
- **Oluşturulacak Dosyalar:** `adapters/llm/prompt_registry.py`, `config/prompts/department_matching.prompt.md`, `experience_inference.prompt.md`, `company_scoring.prompt.md`, `ai_match_rationale.prompt.md`.
- **Bileşenler:** LLM Gateway (prompt katmanı).
- **Bağımlılıklar:** M5.1.
- **Beklenen Sonuç:** Şablonlar dosyadan yüklenir, değişken yer tutucuları doğru doldurulur; kod içinde hiçbir prompt metni gömülü değildir.
- **Tamamlanma Doğrulaması:** Birim testi her şablonun örnek değişkenlerle doğru render edildiğini doğrular.
- **Tahmini Süre:** 3–5 saat (ilk prompt yazımı/iterasyonu dahil).

### M5.3 — LLM Gateway (Kademelendirme + Doğrulama + Repair)
- **Amaç:** Model kademelendirmesini (TDD Section 10 tablosu), yapılandırılmış çıktı doğrulamasını ve tek seferlik "repair" yeniden istemini uygulamak.
- **Oluşturulacak Dosyalar:** LLM Gateway mantığı (`adapters/llm/anthropic_adapter.py` üzerine inşa edilir; gerekirse ayrı bir `llm/gateway.py`).
- **Bileşenler:** LLM Gateway.
- **Bağımlılıklar:** M5.1, M5.2.
- **Beklenen Sonuç:** Bozuk çıktı bir kez "repair" ile düzeltilmeye çalışılır; yine başarısız olursa "Scoring Unavailable" ile zarifçe geri döner — asla uydurma bir skor üretmez (RISK-10).
- **Tamamlanma Doğrulaması:** Sahte (mock) bir provider ile: (a) önce bozuk sonra geçerli JSON döndüren senaryoda repair yolunun kullanıldığı, (b) iki kez de bozuk döndüren senaryoda hatasız "Scoring Unavailable" sonucunun döndüğü doğrulanır.
- **Tahmini Süre:** 5–8 saat.

---

## Faz 6 — Filtreleme

### M6.1 — Blacklist Filtresi
- **Amaç:** FR-19'u uygulamak — dışlanan şirket/ilan diğer tüm filtrelerden önce elenir.
- **Oluşturulacak Dosyalar:** `filtering/blacklist_filter.py`.
- **Bileşenler:** Filtering Pipeline.
- **Bağımlılıklar:** M2.2.
- **Beklenen Sonuç:** Blacklist'teki bir şirket/ilan anında ve doğru gerekçeyle elenir.
- **Tamamlanma Doğrulaması:** Blacklist'e alınmış bir şirket fixture'ı ile birim testi.
- **Tahmini Süre:** 1–2 saat.

### M6.2 — Lokasyon Filtresi
- **Amaç:** FR-3/Section 11.1'i, EDGE-3 fallback'i dahil uygulamak.
- **Oluşturulacak Dosyalar:** `filtering/location_filter.py`.
- **Bileşenler:** Filtering Pipeline.
- **Bağımlılıklar:** M1.1.
- **Beklenen Sonuç:** İstanbul on-site/hybrid, İstanbul dışı, ve belirsiz ("Remote - Turkey") durumları doğru sınıflandırılır.
- **Tamamlanma Doğrulaması:** Bu dört senaryoyu kapsayan birim testleri.
- **Tahmini Süre:** 2–3 saat.

### M6.3 — Deneyim Seviyesi Filtresi
- **Amaç:** FR-5'i, kural tabanlı + LLM fallback (EDGE-1) ve başlık/açıklama çelişki önceliğini (EDGE-12) dahil uygulamak.
- **Oluşturulacak Dosyalar:** `filtering/experience_filter.py`.
- **Bileşenler:** Filtering Pipeline, LLM Gateway.
- **Bağımlılıklar:** M6.2, M5.3.
- **Beklenen Sonuç:** Açık kıdem sinyali olan ilanlar elenir; Management Trainee istisnası korunur; çelişkili sinyalde açıklama esas alınır.
- **Tamamlanma Doğrulaması:** Birim testleri: açık kıdemli başlık → red; Management Trainee → kabul; çelişkili başlık/açıklama → açıklamaya göre kabul; belirsiz durum → LLM yoluna (mock) yönlendirilir.
- **Tahmini Süre:** 4–6 saat.

### M6.4 — Departman Filtresi (Semantik)
- **Amaç:** FR-4'ü, altı küme ve 0.65 varsayılan eşikle, iki dilli (EDGE-2) olarak uygulamak.
- **Oluşturulacak Dosyalar:** `filtering/department_filter.py`.
- **Bileşenler:** Filtering Pipeline, LLM Gateway.
- **Bağımlılıklar:** M6.3, M5.3.
- **Beklenen Sonuç:** Listede birebir olmayan ama anlamca yakın unvanlar (TR/EN) doğru güven skoruyla yakalanır.
- **Tamamlanma Doğrulaması:** 15–20 başlık/açıklama çiftinden oluşan küratörlü bir test seti (tam eşleşme, yakın-anlamsal eşleşme, açık eşleşmeme, her iki dilde) manuel olarak beklenen sonuçlarla karşılaştırılır.
- **Tahmini Süre:** 4–6 saat.

### M6.5 — Filtreleme Zinciri Montajı
- **Amaç:** Blacklist→Location→Experience→Department sırasını tek bir birim olarak birleştirmek (TDD Section 11.4'ün inceltilmiş sırası).
- **Oluşturulacak Dosyalar:** `filtering/pipeline.py`.
- **Bileşenler:** Filtering Pipeline.
- **Bağımlılıklar:** M6.1–M6.4.
- **Beklenen Sonuç:** Karma bir ilan grubu tek bir çağrıyla sırayla filtrelenir; her ilan için `FilterResultDetail` üretilir.
- **Tamamlanma Doğrulaması:** Entegrasyon testi, elle hesaplanmış beklenen pass/reject/borderline dağılımıyla karşılaştırılır.
- **Tahmini Süre:** 2–3 saat.

---

## Faz 7 — Skorlama

### M7.1 — Şirket Kalite Puanlama + Önbellek
- **Amaç:** Section 12.1 rubriğini, Unrated yeniden normalizasyonunu (12.3) ve düzeltilmiş 3 parçalı önbellek anahtarını (`company_id`, `weight_profile_id`, `rubric_version` — TDD v1.1 Fix 3) uygulamak.
- **Oluşturulacak Dosyalar:** `scoring/company_scoring.py`, `scoring/score_cache.py` (şirket tarafı).
- **Bileşenler:** Company Scoring Service, LLM Gateway.
- **Bağımlılıklar:** M5.3, M1.3.
- **Beklenen Sonuç:** Aynı `rubric_version` ile ikinci puanlama önbellekten gelir; `rubric_version` değiştiğinde yeniden hesaplanır; Unrated durumunda ağırlık yeniden normalizasyonu Section 12.3 formülüyle birebir örtüşür.
- **Tamamlanma Doğrulaması:** Birim testleri — aynı ağırlık/rubric_version ile iki çağrı → ikincisi cache hit (LLM mock'unun bir kez çağrıldığı doğrulanır); `rubric_version` değişince cache miss; Unrated senaryosunda ağırlık matematiği elle hesaplananla eşleşir.
- **Tahmini Süre:** 5–7 saat.

### M7.2 — AI Match Skorlama (Yapısal Sinyal + Deterministik Formül)
- **Amaç:** "LLM sinyal çıkarır, kod skoru hesaplar" kararını (TDD Section 10) ve FR-18'in Job-seviyesi önbellek anahtarını (`Job ID + Account ID + Config Version`) uygulamak; grounded gerekçe üretimini gerçekleştirmek.
- **Oluşturulacak Dosyalar:** `scoring/ai_matching.py`.
- **Bileşenler:** AI Matching Service, LLM Gateway.
- **Bağımlılıklar:** M7.1, M6.5.
- **Beklenen Sonuç:** Bir ilan, ≥3 gerekçe maddesiyle 0-100 arası bir skor alır; aynı girdiyle tekrar çalıştırıldığında ek LLM çağrısı yapılmadan aynı skor üretilir.
- **Tamamlanma Doğrulaması:** Sahte LLM sinyalleriyle birim testi — ağırlıklı toplam formülü elle hesaplanan beklenen skorla birebir eşleşir; gerekçe maddelerinin yalnızca sinyal setindeki alanlara atıfta bulunduğu doğrulanır; aynı girdi iki kez çalıştırılır, ikinci seferde LLM çağrısı yapılmadığı (cache hit) doğrulanır.
- **Tahmini Süre:** 6–9 saat.

### M7.3 — Borderline Bucket Mantığı
- **Amaç:** FR-16'nın bant genişliği mantığını filtreleme ve AI Match Score arasında tek bir `is_borderline` bayrağında birleştirmek.
- **Oluşturulacak Dosyalar:** `scoring/ai_matching.py` içine borderline hesaplaması eklenir (yeni dosya yok).
- **Bileşenler:** AI Matching Service.
- **Bağımlılıklar:** M7.2.
- **Beklenen Sonuç:** EDGE-11'deki "eşik 60 iken skor 58" senaryosu doğru şekilde Borderline'a düşer, elenmez.
- **Tamamlanma Doğrulaması:** 60 eşik / 5 bant konfigürasyonuna karşı 58, 60, 65 skorlarının sırasıyla Borderline/Pass/Pass olarak sınıflandığı doğrulanır.
- **Tahmini Süre:** 2–3 saat.

---

## Faz 8 — Sıralama & Raporlama

### M8.1 — Sıralama ve Gruplama
- **Amaç:** FR-11'i uygulamak — departman bazlı gruplama + Top N; Closed/Excluded durumundaki ilanları dışlamak.
- **Oluşturulacak Dosyalar:** `ranking/ranker.py`.
- **Bileşenler:** Ranking Service.
- **Bağımlılıklar:** M7.3.
- **Beklenen Sonuç:** Karma durumlu bir ilan setinden Closed/Excluded olanlar hem grup hem Top-N çıktısında görünmez; Top-N, AI Match Score'a göre azalan sıradadır.
- **Tamamlanma Doğrulaması:** Karma fixture ile birim testi.
- **Tahmini Süre:** 2–3 saat.

### M8.2 — Rapor Şablonu + Derleyici
- **Amaç:** Section 16'nın tam yapısını (Top Matches, departman bölümleri, "Previously Reported", Bootstrap dalı — FR-20) uygulamak.
- **Oluşturulacak Dosyalar:** `reporting/compiler.py`, `reporting/templates/markdown_report.template.md`.
- **Bileşenler:** Reporting Compiler.
- **Bağımlılıklar:** M8.1, M1.3.
- **Beklenen Sonuç:** Sabit bir fixture'dan PRD Section 16.2'nin iskeletine uyan gerçek bir Markdown çıktısı üretilir.
- **Tamamlanma Doğrulaması:** Golden-file testi — çıktının, önceden onaylanmış beklenen bir Markdown dosyasıyla farkı olmadığı doğrulanır; boş geçmiş fixture'ıyla Bootstrap dalının tetiklendiği ayrıca doğrulanır.
- **Tahmini Süre:** 4–6 saat.

### M8.3 — ReportStore + Kalıcılık
- **Amaç:** FR-17'yi uygulamak — her rapor kendi dosyasında, üzerine yazılmadan kalıcı hale gelir.
- **Oluşturulacak Dosyalar:** `ports/report_store_port.py`, `adapters/reporting/filesystem_report_store.py`.
- **Bileşenler:** ReportStore Adapter.
- **Bağımlılıklar:** M8.2, M2.2.
- **Beklenen Sonuç:** İki ardışık derleme, iki ayrı dosya ve iki ayrı `reports` satırı (doğru `config_snapshot_ref` ile) üretir.
- **Tamamlanma Doğrulaması:** Derleyici arka arkaya iki kez çalıştırılır; iki farklı dosya ve iki farklı DB satırı doğrulanır.
- **Tahmini Süre:** 2–3 saat.

---

## Faz 9 — Orkestrasyon & Zamanlama

### M9.1 — RunLock
- **Amaç:** FR-12'nin çakışma önleme garantisini, `lock_expires_at` zaman aşımı dahil (TDD v1.1 Fix 5) uygulamak.
- **Oluşturulacak Dosyalar:** `run/run_lock.py`.
- **Bileşenler:** RunLock.
- **Bağımlılıklar:** M1.3.
- **Beklenen Sonuç:** İkinci bir eşzamanlı çalıştırma reddedilir; süresi dolmuş bir kilit otomatik olarak geçersiz sayılır.
- **Tamamlanma Doğrulaması:** Kilidi al, ikinci alım denemesinin reddedildiğini doğrula; `lock_expires_at`'i geçmişe ayarlayıp üçüncü denemenin başarılı olduğunu doğrula.
- **Tahmini Süre:** 2–3 saat.

### M9.2 — Company Score Repository
- **Amaç:** FR-18/PRD Section 12.4'ün şirket-seviyesi skor önbellekleme gereksinimini karşılamak için `CompanyScore`'a (M7.1) kalıcılık kazandırmak — `CompanyScoreOrm` (M1.2) zaten var ama onu saran bir port/repository yok. Yalnızca kalıcılık eklenir: `score_company()`, `score_cache.py` ve Company Quality puanlama kuralları (Section 12.1'in altı boyutu/ağırlıkları) hiçbir şekilde değiştirilmez. Tazelik penceresi (freshness window) değerlendirmesi bu milestone'un kapsamı dışındadır — bu Port ham `get_by_key` sonucunu döner, `evaluated_at`'in `Thresholds.company_score_reevaluation_window_days` içinde olup olmadığına karar vermek Orchestrator'ın (M9.3) sorumluluğunda kalır.
- **Oluşturulacak Dosyalar:** `ports/company_score_repository_port.py`, `db/repositories/company_score_repository.py`.
- **Bileşenler:** Company Score Repository.
- **Bağımlılıklar:** M1.2, M7.1.
- **Beklenen Sonuç:** Bir `CompanyScore`, `company_id + weight_profile_id + rubric_version` bileşik anahtarıyla kalıcı olarak oluşturulabilir, okunabilir ve güncellenebilir.
- **Tamamlanma Doğrulaması:** Birim testleri (gerçek test DB'sine karşı): bir `CompanyScore` oluşturulur ve aynı anahtarla `get_by_key` ile geri okunur; farklı bir `rubric_version` veya `weight_profile_id` ile aynı `company_id`'nin AYRI bir kayıt oluşturduğu (Section 12.4 çok-kullanıcılı önbellekleme kuralı) doğrulanır; `update()` var olan kaydı değiştirir; `get_by_key` bulunamayan bir anahtar için `None` döner.
- **Tahmini Süre:** 3–4 saat.

### M9.3 — Run Orchestrator (Uçtan Uca Kablo)
- **Amaç:** Collection→Normalization→History→Filtering→Scoring→Ranking→Reporting→State Update'i tek bir çağrıda birleştirmek; "eager cache, atomic final state" transaction sınırını (Section 17) ve merkezi hata sınıflandırmasını (Section 20) uygulamak.
- **Oluşturulacak Dosyalar:** `run/orchestrator.py`.
- **Bileşenler:** Run Orchestrator (tüm önceki servisler).
- **Bağımlılıklar:** Faz 3–8'in tamamı, M9.1, M9.2.
- **Beklenen Sonuç:** Tek bir fonksiyon çağrısı, bir `AccountContext` için tam bir döngüyü uçtan uca çalıştırır.
- **Tamamlanma Doğrulaması:** İlk gerçek entegrasyon testi — küçük/kontrollü bir fixture'a (veya `max_jobs=3` ile sınırlı gerçek bir LinkedIn çalıştırmasına) karşı çalıştırılır; bir rapor dosyası + doğru `run_logs` satırı + doğru `evaluated_jobs` satırları doğrulanır. Ayrıca pipeline ortasında kasıtlı bir hata tetiklenip `evaluated_jobs`/`reports`/`run_logs`'un değişmediği (atomiklik) doğrulanır.
- **Tahmini Süre:** 6–10 saat.

### M9.4 — Hata Sınıflandırma + Retry
- **Amaç:** Section 20'nin `TransientError`/`PermanentError`/`PartialRecordError` taksonomisini ve Section 21'in backoff/circuit-breaker-lite mekanizmasını LinkedIn ve LLM çağrı noktalarına uygulamak.
- **Oluşturulacak Dosyalar:** Ortak bir retry/backoff yardımcı modülü; M3.3 ve M5.1'deki çağrı noktaları bu modülü kullanacak şekilde güncellenir.
- **Bileşenler:** Run Orchestrator, Collection Service, LLM Gateway.
- **Bağımlılıklar:** M9.3.
- **Beklenen Sonuç:** Geçici hatalar otomatik olarak yeniden denenir; ardışık hata eşiği aşılınca toplama erken durur ve Run "Partial" işaretlenir.
- **Tamamlanma Doğrulaması:** Sahte bir "önce N kez başarısız, sonra başarılı" istemciyle doğru retry sayısı/zamanlaması; her zaman başarısız bir istemciyle devre kesicinin erken durup Run'ı Partial işaretlediği doğrulanır.
- **Tahmini Süre:** 4–6 saat.

### M9.5 — Loglama (Yapılandırılmış + Redaksiyon)
- **Amaç:** FR-15/NFR-10'un gözlemlenebilirlik sözleşmesini gerçek kılmak.
- **Oluşturulacak Dosyalar:** `logging/structured_logger.py`; önceki modüllere loglama çağrıları eklenir.
- **Bileşenler:** Structured Logger.
- **Bağımlılıklar:** M9.3.
- **Beklenen Sonuç:** Her ERROR, `run_logs.error_detail`'i doldurur; hiçbir secret log satırında görünmez.
- **Tamamlanma Doğrulaması:** Kasıtlı olarak geçersiz bir secret ile çalıştırma yapılıp log dosyası grep'lenerek redaksiyon doğrulanır; bir hata tetiklenip `error_detail`'in dolu olduğu doğrulanır.
- **Tahmini Süre:** 3–4 saat.

### M9.6 — Scheduler Port + APScheduler Adapter
- **Amaç:** FR-12'nin otomatik çizelgesini ve NFR-14'ün jitter'ını, `next_run_at` kalıcılığı (TDD v1.1 Fix 5) dahil uygulamak.
- **Oluşturulacak Dosyalar:** `ports/scheduler_port.py`, `adapters/scheduling/apscheduler_adapter.py`.
- **Bileşenler:** Scheduling Service.
- **Bağımlılıklar:** M9.3, M9.1.
- **Beklenen Sonuç:** Kısa bir test aralığıyla (örn. 2 dakika) çizelge, jitter penceresi içinde otomatik olarak tetiklenir; `next_run_at` süreç yeniden başlatıldığında korunur.
- **Tamamlanma Doğrulaması:** Kısa aralıklı manuel test; yeniden başlatma sonrası çizelgenin kaybolmadığının doğrulanması.
- **Tahmini Süre:** 3–5 saat.

### M9.7 — CLI Genişletmesi (Manuel Tetikleme)
- **Amaç:** FR-12'nin manuel tetiklemesini, otomatik çizelgeden bağımsız olarak eklemek.
- **Oluşturulacak Dosyalar:** `cli.py`'ye `run` komutu eklenir.
- **Bileşenler:** CLI, Run Orchestrator, RunLock.
- **Bağımlılıklar:** M9.3, M9.1.
- **Beklenen Sonuç:** Zamanlayıcı boştayken manuel çalıştırma başarılı olur; bir çalıştırma zaten sürüyorken manuel tetikleme anlaşılır bir mesajla reddedilir.
- **Tamamlanma Doğrulaması:** Her iki senaryonun manuel testi.
- **Tahmini Süre:** 2–3 saat.

---

## Faz 10 — Paketleme & İlk Çalıştırma

### M10.1 — Docker Compose Tamamlama + Yedekleme
- **Amaç:** Tam sistemi (`app` + `db`) gözetimsiz çalışır hale getirmek; zamanlanmış `pg_dump` yedeklemesini eklemek (Section 27).
- **Oluşturulacak Dosyalar:** `docker-compose.yml` (tamamlanmış), `Dockerfile` (tamamlanmış), yedekleme script'i.
- **Bileşenler:** Dağıtım altyapısı.
- **Bağımlılıklar:** Yukarıdaki tüm milestone'lar.
- **Beklenen Sonuç:** `docker compose up` tüm sistemi çalıştırır.
- **Tamamlanma Doğrulaması:** Temiz bir makinede/VM'de soğuk başlatma yapılır; tohumlanmış hesap, zamanlanmış bir çalıştırma ve bir yedek dosyasının (M3.1'deki tek seferlik LinkedIn girişi dışında) manuel müdahale olmadan ortaya çıktığı doğrulanır.
- **Tahmini Süre:** 3–5 saat.

### M10.2 — İlk Gerçek Uçtan Uca Çalıştırma (Bootstrap Run)
- **Amaç:** Gerçek LinkedIn hesabı ve gerçek config ile sistemi ilk kez tam kapasiteyle çalıştırmak.
- **Oluşturulacak Dosyalar:** Yok — bu bir doğrulama milestone'udur.
- **Bileşenler:** Sistemin tamamı.
- **Bağımlılıklar:** M10.1.
- **Beklenen Sonuç:** FR-20'nin Bootstrap raporu gerçek veriyle üretilir; kullanıcı raporun kalitesini (G-2/G-3) ilk kez gerçek çıktı üzerinden değerlendirir.
- **Tamamlanma Doğrulaması:** Üretilen rapor, PRD Section 5'teki başarı metrikleri ışığında manuel olarak incelenir (ilanlar mantıklı mı, gerekçeler tutarlı mı, Company Quality Score makul mü).
- **Tahmini Süre:** 2–4 saat (çoğunlukla insan incelemesi + ASM-7'nin öngördüğü config ince ayarı).

---

## Sonraki Adımlar

Bu roadmap yalnızca **V1 (MVP)** kapsamını kapsar. Faz 10 tamamlandığında sistem PRD'nin tüm Must-have ve Should-have gereksinimlerini (FR-1–FR-21, NFR-1–NFR-15) karşılar durumdadır. PRD Section 18'deki Phase 2–4 özellikleri (bildirimler, CV optimizasyonu, vb.) bu roadmap'in kapsamı dışındadır ve TDD Section 29'daki genişletme noktaları üzerinden ayrı bir roadmap turunda ele alınmalıdır.
