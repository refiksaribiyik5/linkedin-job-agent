# LinkedInBot — Technical Design Document (TDD)

### Document Control

| Alan | Değer |
|---|---|
| Doküman Türü | Technical Design Document (Living Document) |
| Proje Kod Adı | LinkedInBot |
| Versiyon | 1.1 |
| Durum | Draft — Implementation-Ready |
| Kaynak PRD | LinkedInBot-PRD.md, **v1.3** |
| Product Owner / Tek Kullanıcı | Refik Sarıbıyık |
| Son Güncelleme | 2026-08-07 |
| Kapsam | V1 (MVP) teknik mimarisi + SaaS'a geçiş için hazırlanmış genişletme noktaları |

---

## 0. Amaç ve Kapsam

PRD (v1.2) sistemin **ne** yapması ve **neden** yapması gerektiğini tanımlar. Bu belge, o gereksinimlerin **nasıl** karşılanacağını tanımlar: somut teknoloji seçimleri, bileşen sınırları, veri şeması, servisler arası akış ve mühendislik kararları.

**Kapsam dışı değildir — bilinçli olarak buraya taşınmıştır:** Platform seçimi, kod organizasyonu, veritabanı şeması, harici entegrasyon detayları — PRD'nin kapsam dışı bıraktığı her şey burada karara bağlanır.

**Bu belge kod veya pseudokod içermez.** Tüm açıklamalar mimari bileşenler, arayüzler (interface/port isimleri), veri akışları ve mühendislik gerekçeleri düzeyindedir; okuyucu bu belgeyi okuduktan sonra doğrudan kodlamaya başlayabilecek netlikte olmalıdır, ancak kodun kendisini bu belgede bulmayacaktır.

**Gösterim kuralı:** Her büyük tasarım kararının hemen altında bir **Gerekçe:** satırı bulunur. Bazı kararlar için ayrıca **Alternatifler:** satırı, değerlendirilip elenen seçenekleri ve neden elendiklerini özetler.

**Traceability:** Bu belge boyunca PRD'deki kimlikler (FR-x, NFR-x, RISK-x, EDGE-x, Section x) referans olarak kullanılır. Appendix A, PRD gereksinimlerini bu belgedeki bileşenlere eşleyen bir izlenebilirlik matrisidir.

---

## Table of Contents

0. [Amaç ve Kapsam](#0-amaç-ve-kapsam)
1. [Mimari Yaklaşım Özeti](#1-mimari-yaklaşım-özeti)
2. [Teknoloji Yığını ve Gerekçeler](#2-teknoloji-yığını-ve-gerekçeler)
3. [Genel Sistem Mimarisi](#3-genel-sistem-mimarisi)
4. [Yüksek Seviye Bileşen Diyagramı](#4-yüksek-seviye-bileşen-diyagramı)
5. [Proje / Klasör Yapısı](#5-proje--klasör-yapısı)
6. [Modül Sorumlulukları](#6-modül-sorumlulukları)
7. [İç Servisler](#7-i̇ç-servisler)
8. [Veri Akışı (End-to-End)](#8-veri-akışı-end-to-end)
9. [LinkedIn Toplama (Scraping) Pipeline'ı](#9-linkedin-toplama-scraping-pipelinei)
10. [AI Değerlendirme Pipeline'ı](#10-ai-değerlendirme-pipelinei)
11. [Filtreleme Pipeline'ı](#11-filtreleme-pipelinei)
12. [Zamanlama Mimarisi](#12-zamanlama-mimarisi)
13. [Konfigürasyon Mimarisi](#13-konfigürasyon-mimarisi)
14. [Multi-User Hazır Mimari](#14-multi-user-hazır-mimari)
15. [Veritabanı Tasarımı ve Şema](#15-veritabanı-tasarımı-ve-şema)
16. [Varlık İlişkileri (ER)](#16-varlık-i̇lişkileri-er)
17. [Durum Yönetimi (State Management)](#17-durum-yönetimi-state-management)
18. [Rapor Üretim Akışı](#18-rapor-üretim-akışı)
19. [Loglama Stratejisi](#19-loglama-stratejisi)
20. [Hata Yönetimi Stratejisi](#20-hata-yönetimi-stratejisi)
21. [Retry Mekanizmaları](#21-retry-mekanizmaları)
22. [Rate Limiting Stratejisi](#22-rate-limiting-stratejisi)
23. [Konfigürasyon Yükleme](#23-konfigürasyon-yükleme)
24. [Secrets Yönetimi](#24-secrets-yönetimi)
25. [Harici Entegrasyonlar](#25-harici-entegrasyonlar)
26. [Güvenlik Değerlendirmeleri](#26-güvenlik-değerlendirmeleri)
27. [Dağıtım Mimarisi](#27-dağıtım-mimarisi)
28. [Ölçeklenebilirlik Değerlendirmeleri](#28-ölçeklenebilirlik-değerlendirmeleri)
29. [Gelecek Genişletilebilirlik Değerlendirmeleri](#29-gelecek-genişletilebilirlik-değerlendirmeleri)
- [Appendix A: Gereksinim → Bileşen İzlenebilirlik Matrisi](#appendix-a-gereksinim--bileşen-i̇zlenebilirlik-matrisi)
- [Appendix B: Teknik Sözlük](#appendix-b-teknik-sözlük)
- [Appendix C: Version History](#appendix-c-version-history)

---

## 1. Mimari Yaklaşım Özeti

Aşağıdaki üç karar, bu belgedeki hemen hemen her bölümü şekillendirir; bu yüzden en başta, tek yerde özetlenir.

**Karar 1 — Modular Monolith (Mikroservis Değil).** V1, tek bir dağıtılabilir süreç/konteyner olarak çalışır; içindeki modüller (Collection, Filtering, Scoring, Reporting, vb.) ayrı ağ servisleri değil, net sınırları olan Python paketleridir.
**Gerekçe:** Tek kullanıcılı bir sistemde mikroservis mimarisi (ağ çağrıları, servis keşfi, dağıtık izleme) NFR-1 (Performance) ve genel bakım yükü açısından karşılığı olmayan bir karmaşıklık maliyetidir. PRD'nin "hız veya özellik genişliği değil, isabet ve şeffaflık" önceliğiyle (Section 1) de uyumludur.

**Karar 2 — Hexagonal Architecture (Ports & Adapters).** Çekirdek iş mantığı (filtreleme, skorlama, raporlama, zamanlama kararı) hiçbir zaman somut bir teknolojiye (Playwright, Postgres, Anthropic API, APScheduler) doğrudan bağımlı değildir; bunun yerine soyut arayüzlere (**port**) bağımlıdır. Somut teknolojiler bu arayüzleri uygulayan **adapter**'lardır.
**Gerekçe:** Bu, PRD'nin NFR-15 (Multi-Tenancy Readiness) ve NFR-8 (Extensibility) gereksinimlerini karşılamanın somut mekanizmasıdır — bir adaptörü değiştirmek (örn. APScheduler → dağıtık kuyruk, yerel dosya sistemi → S3) çekirdek mantığı hiç etkilemez. Bu belge boyunca "X Port" ve "X Adapter" terimleri bu ayrımı ifade eder.

**Karar 3 — Hesap-Parametrik Çekirdek (Account-Parameterized Core).** Sistemin hiçbir iç bileşeni "kullanıcı" kavramını zımni/global bir varsayım olarak taşımaz. Her çalıştırma açıkça bir `AccountContext` (hesap kimliği + o hesabın çözümlenmiş konfigürasyon profili) alır ve tüm servis çağrıları bu bağlamı parametre olarak taşır.
**Gerekçe:** PRD Section 15.0 / 17.1 / NFR-15'in doğrudan teknik karşılığıdır. V1'de tek bir `AccountContext` üretilip pipeline'a verilir; ikinci bir hesap eklemek, ikinci bir `AccountContext` üretip aynı pipeline'ı onunla çalıştırmaktan ibarettir — çekirdek kodun değişmesini gerektirmez.

---

## 2. Teknoloji Yığını ve Gerekçeler

| Katman | Seçim | Gerekçe | Değerlendirilip Elenen Alternatifler |
|---|---|---|---|
| Dil / Runtime | **Python 3.12+** | Olgun tarayıcı otomasyonu (Playwright), zengin veri/AI SDK ekosistemi (Anthropic SDK), Pydantic ile güçlü tip/şema doğrulama (FR-13'ün doğrudan karşılığı), tek geliştirici için düşük bilişsel yük | Node.js/TypeScript (eşit derecede uygulanabilir; Python'ın Pydantic+SQLAlchemy ekosistemi skor/konfig-ağırlıklı bu alan için hafif üstün bulundu); n8n/low-code (FR-13'ün versiyonlanabilir, test edilebilir konfigürasyon gereksinimiyle ve "kısa vadeli kolaylık yerine genişletilebilirlik" talimatıyla çelişir) |
| Tarayıcı Otomasyonu | **Playwright (Python)** | LinkedIn ağır JS tabanlı bir SPA; Playwright kalıcı oturum (storage state), otomatik bekleme ve aktif bakım sunar; resmi/belgesiz API'lere göre yapısal değişikliklere (RISK-2) karşı daha dayanıklı bir soyutlama sağlar | Doğrudan HTTP + reverse-engineered private API (RISK-2'yi artırır, oturum/JS-render edilen alanlarla uyumsuz) |

**Netleştirme (M10.2, bağımsız incelemede bulunan bir bulgunun sonucu):** yukarıdaki "Doğrudan HTTP + reverse-engineered private API" reddi, Playwright'i TAMAMEN by-pass edip bağımsız, elle üretilmiş HTTP istekleri (özel başlıklar/CSRF token/çerez yönetimi elle taklit edilerek) göndermeyi kapsar — reddin gerekçesi olan "oturum/JS-render edilen alanlarla uyumsuzluk" ve RISK-2 artışı doğrudan BU senaryoya özgüdür (gerçek bir tarayıcı/oturum olmadan, LinkedIn'in JS'inin ürettiği durumu taklit etmeye çalışmak). M10.2'de canlı olarak doğrulanan, ayrı bir bulgu: LinkedIn'in kendi istemci tarafı React arayüzü, kendi API'sinden başarıyla getirdiği veriyi DOM'a monte ederken bir hydration hatasına (üretim ortamında "Minified React error #418" olarak gözlemlendi) uğruyor — DOM'dan ayrıştırma bu yüzden güvenilmez hale geldi, LinkedIn'in KENDİ API'si değil. Buna karşılık, `adapters/linkedin/playwright_client.py` Playwright'in yönettiği AYNI, gerçek, oturum-tabanlı tarayıcı gezintisinin (goto/session/auth TAMAMEN Playwright'in sorumluluğunda kalır) doğal bir sonucu olarak ZATEN alınan ağ yanıtı gövdelerini (örn. `voyagerJobsDashJobCards`) okur — bağımsız/elle üretilmiş hiçbir istek YOKTUR, Playwright'in kalıcı oturum/otomatik bekleme/aktif bakım avantajlarının HİÇBİRİ kaybedilmez. Bu, reddedilen alternatiften YAPISAL olarak farklıdır: "hangi katmandan (DOM mu, ağ yanıtı mı) okunduğu" kararı, TDD Section 6/9'un `adapters.linkedin`'i zaten Playwright detaylarının izole edildiği tek yer olarak tanımlamasının kapsamı İÇİNDE kalır - yeni bir Port, yeni bir bağımlılık yönü veya `collection`/`session_manager`'da bir değişiklik GEREKTİRMEZ.
| Veritabanı | **PostgreSQL 16** | NFR-15/Section 15.0'ın Account-Scoped/Shared veri ayrımı, JSONB ile esnek ağırlık/gerekçe/config alanları, ileride Row-Level Security (RLS) ile çok-kiracılı izolasyona doğrudan geçiş imkânı | **SQLite** (bilinçli olarak elendi: V1 için daha basit olurdu, ancak "kısa vadeli kolaylık yerine SaaS hazırlığı" talimatı gereği, eşzamanlı yazma ve RLS tabanlı kiracı izolasyonu Postgres'te doğal, SQLite'ta sonradan acılı bir geçiş gerektirir) |
| ORM / Migration | **SQLAlchemy 2.x + Alembic** | Versiyonlanmış, geri alınabilir şema evrimi (Section 17'deki Config Snapshot ve gelecekteki SaaS şema değişiklikleri için gerekli) | Ham SQL (versiyon kontrolü ve tip güvenliği kaybı) |
| Config/Domain Şeması | **Pydantic v2** | FR-13'ün "geçersiz konfigürasyonu çalıştırma başlamadan reddet" kabul kriterinin doğrudan altyapısı; aynı modeller pipeline aşamaları arası veri taşıyıcı (DTO) olarak da kullanılır | Serbest dict/YAML okuma (tip güvenliği ve doğrulama yok) |
| LLM Sağlayıcı | **Anthropic Claude API** (varsayılan), `LLMProvider` arayüzü arkasında | Güçlü yapılandırılmış çıktı desteği (FR-7'nin gerekçe-madde grounding gereksinimini destekler), maliyet/kalite için model kademelendirmeye uygun ürün ailesi (bkz. Section 10) | Tek bir sağlayıcıya sıkı bağımlılık (RISK-9 Cost Escalation'ı ağırlaştırır) — bu yüzden soyutlama katmanı zorunlu tutuldu, sağlayıcı kilitlenmesi değil |
| Zamanlama | **APScheduler (in-process)**, `SchedulerPort` arkasında | V1 tek hesaplı; ayrı bir mesaj kuyruğu/dağıtık zamanlayıcı altyapısı olmadan jitter (NFR-14) ve DB tabanlı kilitle çakışma önleme (Section 14) sağlar | Celery Beat + Redis (V1'in ölçeğinde gereksiz operasyonel yük; SaaS fazında öngörülen yükseltme yolu — bkz. Section 28) |
| Secrets | **Yerel şifreli secrets deposu** (OS keyring destekli), `SecretsProvider` arkasında | Tek makineli kişisel dağıtım için barındırılan bir secrets servisi gereksiz maliyet; arayüz soyutlaması SaaS fazında AWS Secrets Manager/Vault'a geçişi kod değişikliği gerektirmeden sağlar | Düz metin `.env` (NFR-3 ihlali); barındırılan KMS (V1 ölçeği için aşırı mühendislik) |
| Dağıtım | **Docker Compose (tek host)** | Playwright + Python + Postgres'i taşınabilir, tekrarlanabilir bir birim haline getirir; SaaS fazındaki konteyner-orkestrasyon (Kubernetes/ECS) geçişiyle aynı temel birimi kullanır | Çıplak metal kurulum (taşınabilirlik ve "prod'a geçişte yeniden yazım" riski) |
| Rapor Deposu | **Dosya sistemi (V1)**, `ReportStore` arayüzü arkasında | FR-17'nin kalıcı/üzerine yazılmayan dosya gereksinimini karşılar; arayüz S3/Notion/Email adaptörlerine (Phase 2) geçişi izole eder | Doğrudan DB'de büyük metin blob'u (dosya tabanlı tüketim modeliyle — Section 16.1 — daha az uyumlu) |

---

## 3. Genel Sistem Mimarisi

Sistem üç eşmerkezli katman olarak modellenir (hexagonal mimarinin klasik gösterimi):

1. **Domain / Core (çekirdek)** — Section 15'teki varlıkların Pydantic modelleri + saf iş mantığı: filtre kuralları, skor ağırlıklandırma formülleri, durum makineleri (Section 17). Bu katman hiçbir dış kütüphaneye (Playwright, SQLAlchemy, Anthropic SDK) bağımlı değildir; yalnızca Port arayüzlerine bağımlıdır.
2. **Application / Orchestration** — Run Orchestrator ve pipeline servisleri (Collector, Filterer, Scorer, Reporter, vb.). Bu katman, Domain'i Port'lar aracılığıyla dış dünyaya bağlar; PRD Section 10'daki 12 adımlı işlem hattının doğrudan karşılığıdır.
3. **Adapters / Infrastructure** — Port'ların somut uygulamaları: `PlaywrightLinkedInAdapter`, `PostgresRepository`, `AnthropicLLMAdapter`, `APSchedulerAdapter`, `LocalFilesystemReportStore`, `LocalKeyringSecretsProvider`.

**Bağımlılık yönü:** Adapters → Application → Domain. Domain hiçbir zaman Adapters'ı bilmez (Dependency Inversion). Bu, NFR-8/NFR-15'in kod seviyesindeki garantisidir: bir adaptör değişikliği (örn. Postgres → başka bir DB) Domain veya Application katmanında tek satır değişiklik gerektirmez.

**Süreç modeli:** V1'de tek bir uzun ömürlü Python süreci çalışır (`main.py`), içinde: (a) APScheduler'ın arka planda çizelgeyi beklediği bir döngü, (b) manuel tetikleme için bir CLI komutu aynı sürece bir "hemen çalıştır" sinyali gönderir veya ayrı bir kısa ömürlü süreç olarak Orchestrator'ı doğrudan çağırır (RunLock ile çakışma kontrolü her iki yolda da aynıdır).

---

## 4. Yüksek Seviye Bileşen Diyagramı

```
                              ┌───────────────────────────┐
                              │   Scheduler / CLI Trigger  │
                              │ (APScheduler / manuel cmd) │
                              └──────────────┬─────────────┘
                                             │ AccountContext oluşturur
                                             ▼
                              ┌───────────────────────────┐
                              │      Run Orchestrator      │◄────── RunLock (DB)
                              │  (12 adımlı pipeline şefi)  │
                              └──────────────┬─────────────┘
              ┌───────────────┬──────────────┼──────────────┬────────────────┐
              ▼               ▼              ▼              ▼                ▼
      ┌───────────────┐ ┌───────────┐ ┌─────────────┐ ┌────────────┐ ┌─────────────┐
      │  Collection    │ │Normalize- │ │History/Diff │ │ Filtering  │ │  Scoring    │
      │ (LinkedIn Port)│ │  ation    │ │(Content Hash│ │ (3 filtre  │ │ (Company +  │
      │                │ │           │ │  Engine)    │ │  zinciri)  │ │  AI Match)  │
      └───────┬────────┘ └───────────┘ └──────┬──────┘ └─────┬──────┘ └──────┬──────┘
              │                                │              │               │
              │                                └──────┬───────┴───────┬───────┘
              │                                       ▼               ▼
              │                              ┌─────────────────────────────┐
              │                              │        LLM Gateway          │
              │                              │  (LLMProvider Port + Cache) │
              │                              └──────────────┬───────────────┘
              │                                              ▼
              │                                   ┌─────────────────────┐
              │                                   │  Ranking & Grouping  │
              │                                   └──────────┬───────────┘
              │                                              ▼
              │                                   ┌─────────────────────┐
              │                                   │  Reporting Compiler  │
              │                                   └──────────┬───────────┘
              │                                              ▼
              │                                   ┌─────────────────────┐
              │                                   │ ReportStore Port     │
              │                                   │ (Filesystem Adapter) │
              │                                   └──────────┬───────────┘
              │                                              ▼
              └────────────────────────────────► State Update + Run Log
                                                   (tek DB transaction'ı)

  Yatay kesen katman: Config Service · Secrets Provider · Structured Logger
  (yukarıdaki her kutu bu üçüne bağımlı olabilir; şema basitlik için tekrar çizilmedi)
```

**Okuma notu:** Collection ile Scoring/Reporting arasındaki tek "kalıcı" bağ Normalization → History/Diff üzerinden geçer; Filtering ve Scoring modülleri LLM Gateway'i paylaşır (aynı sağlayıcı, farklı prompt/model kademeleri — bkz. Section 10).

---

## 5. Proje / Klasör Yapısı

```
linkedinbot/
├── pyproject.toml
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
├── .env.example
├── config/
│   ├── system.defaults.yaml        # Section 17 sistem varsayılanları
│   ├── accounts/
│   │   └── default.account.yaml    # V1'in tek hesap tohum (seed) verisi
│   └── prompts/
│       ├── department_matching.prompt.md
│       ├── experience_inference.prompt.md
│       ├── company_scoring.prompt.md
│       └── ai_match_rationale.prompt.md
├── migrations/
│   └── versions/                   # Alembic migration geçmişi
├── src/linkedinbot/
│   ├── main.py                     # süreç giriş noktası (scheduler döngüsü)
│   ├── cli.py                      # manuel tetikleme / config doğrulama komutları
│   ├── domain/                     # Section 15 varlıkları — Pydantic modelleri, saf mantık
│   │   ├── job_posting.py
│   │   ├── company_profile.py
│   │   ├── evaluated_job.py
│   │   ├── user_profile.py
│   │   ├── report.py
│   │   ├── run_log.py
│   │   └── account_context.py
│   ├── ports/                      # Soyut arayüzler (Hexagonal "port" katmanı)
│   │   ├── linkedin_port.py
│   │   ├── llm_provider_port.py
│   │   ├── scheduler_port.py
│   │   ├── secrets_provider_port.py
│   │   ├── report_store_port.py
│   │   └── notification_provider_port.py
│   ├── adapters/                   # Somut uygulamalar
│   │   ├── linkedin/
│   │   │   ├── playwright_client.py
│   │   │   └── session_manager.py
│   │   ├── llm/
│   │   │   ├── anthropic_adapter.py
│   │   │   └── prompt_registry.py
│   │   ├── scheduling/
│   │   │   └── apscheduler_adapter.py
│   │   ├── secrets/
│   │   │   └── local_keyring_adapter.py
│   │   ├── reporting/
│   │   │   └── filesystem_report_store.py
│   │   └── notifications/
│   │       └── noop_notification_adapter.py   # Phase 2'ye ayrılmış boş adaptör
│   ├── collection/
│   │   └── collector.py            # Section 10 adım 3
│   ├── normalization/
│   │   └── normalizer.py           # Section 10 adım 4
│   ├── history/
│   │   ├── diff_engine.py          # New/Seen/Updated/Closed (Section 10 adım 5)
│   │   └── content_hasher.py
│   ├── filtering/
│   │   ├── blacklist_filter.py
│   │   ├── location_filter.py
│   │   ├── experience_filter.py
│   │   ├── department_filter.py
│   │   └── pipeline.py             # Section 11.4 sıralı yürütme
│   ├── scoring/
│   │   ├── company_scoring.py      # Section 12
│   │   ├── ai_matching.py          # Section 13
│   │   └── score_cache.py          # Section 12.4 / FR-18
│   ├── ranking/
│   │   └── ranker.py               # Section 10 adım 9
│   ├── reporting/
│   │   ├── compiler.py             # Section 16
│   │   └── templates/markdown_report.template.md
│   ├── run/
│   │   ├── orchestrator.py         # 12 adımlı pipeline şefi
│   │   └── run_lock.py             # Section 14 çakışma önleme
│   ├── config/
│   │   ├── loader.py               # öncelik zinciri + doğrulama (Section 23)
│   │   ├── schema.py               # Pydantic config şemaları
│   │   └── validator.py
│   ├── db/
│   │   ├── engine.py
│   │   ├── models.py               # SQLAlchemy ORM modelleri
│   │   └── repositories/
│   │       ├── account_repository.py
│   │       ├── job_repository.py
│   │       ├── company_repository.py
│   │       ├── evaluated_job_repository.py
│   │       ├── report_repository.py
│   │       └── run_log_repository.py
│   └── logging/
│       └── structured_logger.py
└── tests/
    ├── unit/
    └── integration/
```

**Gerekçe (genel):** `ports/` ve `adapters/` ayrımı, Section 1'deki Hexagonal karar kaydının doğrudan dosya-sistemi karşılığıdır — bir geliştirici "bu bağımlılığı değiştirebilir miyim?" sorusuna klasör ismine bakarak cevap bulur. `domain/` katmanının hiçbir alt klasörü `adapters/`'a import etmez; bu kural bir lint kuralı (import-linter benzeri) ile otomatik denetlenmelidir (bkz. Section 26).

---

## 6. Modül Sorumlulukları

| Modül | Sorumluluk | Bağımlı Olduğu Port(lar) |
|---|---|---|
| `collection` | Section 17 Target Location(s)/Departments kapsamında arama sorguları üretir, `linkedin_port` üzerinden sonuçları çeker, FR-21 üst sınırını uygular, ham `RawJobRecord` akışı üretir | `linkedin_port` |
| `normalization` | Ham veriyi `JobPosting` domain modeline dönüştürür; `content_hash`'i yalnızca FR-14'ün "anlamlı değişiklik" kapsamındaki alanlardan (Title, Experience Level çıkarımı, Location, Workplace Type, Description) hesaplar — görüntülenme sayısı, göreli zaman ifadesi gibi oynak/gürültülü alanlar dahil edilmez (FR-14/FR-18 için temel) | — (saf) |
| `history` | Her `JobPosting`'i geçmişle karşılaştırıp New/Seen/Updated/Closed durumuna atar (FR-8, FR-9, FR-10, FR-14) | `job_repository` |
| `filtering` | Blacklist → Location → Experience → Department sırasıyla filtre zincirini yürütür (Section 11.4 + FR-19 önceliklendirmesi), her ilan için `FilterResultDetail` üretir | `llm_provider_port` (yalnızca Department filtresi) |
| `scoring.company_scoring` | Section 12 rubriğini uygular, Section 12.4 önbellekleme kuralını (Weight Profile + Rubric Version bazlı) uygular | `llm_provider_port`, `company_repository` |
| `scoring.ai_matching` | Section 13 ağırlıklı skor formülünü **deterministik olarak** hesaplar; LLM'den yalnızca alt-sinyalleri (bkz. Section 10) alır | `llm_provider_port`, `evaluated_job_repository` |
| `ranking` | Departman bazlı gruplama + Top N hesaplama (FR-11) | — (saf) |
| `reporting.compiler` | Section 16 formatına uygun Markdown içerik derler, "Previously Reported" tespiti yapar | `report_repository` |
| `reporting` (ReportStore adaptörü) | Derlenen raporu kalıcı, üzerine yazılmayan bir konuma yazar (FR-17) | `report_store_port` |
| `run.orchestrator` | 12 adımlı pipeline'ı `AccountContext` ile uçtan uca yürütür, hata sınıflandırmasını tek noktadan yapar (Section 20), transaction sınırını yönetir (Section 17) | tüm yukarıdaki servisler |
| `run.run_lock` | Section 14 çakışma önlemeyi DB satırı üzerinden uygular | `account_repository` |
| `config` | Section 23'teki öncelik zincirini uygular, Pydantic ile doğrular, `ConfigVersion` üretir | — (DB'ye doğrudan erişir) |
| `db.repositories.*` | Her domain varlığı için CRUD + sorgu arayüzü; `account_id` parametresi olmadan hiçbir Account-Scoped sorgu çalışmaz (bkz. Section 14) | SQLAlchemy Session |
| `logging` | Yapılandırılmış (JSON) loglama kurulumu, secret redaksiyonu (bkz. Section 19, 24) | — |
| `adapters.linkedin` | `linkedin_port`'un Playwright uygulaması; oturum doğrulama/yenileme (FR-1) | Playwright, `secrets_provider_port` |
| `adapters.llm` | `llm_provider_port`'un Anthropic uygulaması; model kademelendirme, prompt şablonlama, yapılandırılmış çıktı doğrulama | Anthropic SDK |
| `adapters.scheduling` | `scheduler_port`'un APScheduler uygulaması; jitter hesaplama (NFR-14) | APScheduler |
| `adapters.secrets` | `secrets_provider_port`'un yerel şifreli uygulaması | OS keyring |
| `adapters.reporting` | `report_store_port`'un dosya sistemi uygulaması | Yerel dosya sistemi |
| `adapters.notifications` | V1'de no-op; Phase 2 için ayrılmış arayüz noktası | — |

---

## 7. İç Servisler

V1 tek bir sürecin içinde çalışan, ancak birbirinden **mantıksal olarak** ayrılmış servisler olarak tasarlanır (mikroservis değil — bkz. Karar 1):

- **Run Orchestrator** — sistemin "beyni"; hangi servisin ne zaman çağrılacağına karar verir, hata durumunda Run status'unu belirler. Tek bir çalıştırmanın tüm yaşam döngüsünden sorumlu tek servistir (bkz. Section 20 — hata sınıflandırmasının neden burada merkezileştiği).
- **Collection Service** — LinkedIn'den ham veri çeker (Section 9).
- **Evaluation Service** (Filtering + Company Scoring + AI Matching'i saran mantıksal gruplama) — bir ilanın "değerlendirilmesi" sürecinin tamamı; LLM Gateway'i ortak kullanır.
- **LLM Gateway** — tüm LLM çağrılarının tek giriş noktası: model seçimi, prompt şablonlama, önbellek kontrolü, yeniden deneme, maliyet loglama (bkz. Section 10). Hiçbir modül Anthropic SDK'sını doğrudan çağırmaz; hepsi LLM Gateway üzerinden geçer — bu, RISK-9/RISK-10 mitigasyonlarının (maliyet takibi, grounding zorunluluğu) **tek yerde** uygulanmasını garanti eder.
- **Reporting Service** — derleme + kalıcı saklama.
- **Scheduling Service** — çizelge hesaplama + kilit yönetimi.
- **Config Service** — konfigürasyon çözümleme + doğrulama.
- **Account Service** — `AccountContext` üretimi; V1'de tek hesabı okur, SaaS fazında hesap listesi üzerinde döner (bkz. Section 14).

**Gerekçe (mantıksal servis ayrımı, fiziksel değil):** Her servisin net bir sorumluluğu ve test edilebilir bir arayüzü olması, gelecekte bunlardan herhangi birinin (en olası aday: Scheduling Service, bkz. Section 28) ayrı bir süreç/deploy birimine çıkarılmasını, geri kalan sistemi bozmadan mümkün kılar.

---

## 8. Veri Akışı (End-to-End)

PRD Section 10'daki 12 adımlı işlem hattının somut servis çağrılarına eşlenmesi:

| # | PRD Adımı | Sorumlu Servis | Girdi | Çıktı |
|---|---|---|---|---|
| 1 | Trigger | Scheduler/CLI | — | `AccountContext` |
| 2 | Session Validation | Collection Service → `linkedin_port` | `AccountContext.secrets_ref` | `SessionStatus` (Valid/Invalid) |
| 3 | Collection | Collection Service | Config (location, keywords, FR-21 limit) | `RawJobRecord[]` |
| 4 | Normalization | Normalization Service | `RawJobRecord[]` | `JobPosting[]` + `content_hash` |
| 5 | Historical Cross-Reference | History/Diff Engine | `JobPosting[]`, geçmiş kayıtlar | `(JobPosting, Status)[]` |
| 6 | Filtering | Filtering Pipeline | yukarıdakiler + Config | `FilterResult[]` (pass/fail/borderline) |
| 7 | Company Scoring | Company Scoring Service | geçen `JobPosting[]`, `CompanyProfile` | `CompanyScore` (veya cache'ten) |
| 8 | AI Matching | AI Matching Service + LLM Gateway | `JobPosting`, `CompanyScore`, `UserProfile`, Config | `EvaluatedJob` (skor + gerekçe) |
| 9 | Ranking & Grouping | Ranking Service | `EvaluatedJob[]` | Departman gruplu + Top N liste |
| 10 | Report Compilation | Reporting Compiler | sıralanmış liste | `Report` (Markdown içerik) |
| 11 | State Update | Orchestrator (tek transaction) | `EvaluatedJob[]`, `Report` | DB'ye yazılmış nihai durum |
| 12 | Logging | Run Log Repository | çalıştırma özeti | `RunLog` satırı |

**Kritik tasarım kararı — "eager cache write, atomic state commit" ayrımı:** Adım 3-8 arasında üretilen ara sonuçlar (ham veri, hesaplanmış skorlar) **hemen ve kalıcı olarak** cache tablolarına yazılır (bkz. Section 17) — bunlar hesaplar arası paylaşılabilir/idempotent verilerdir, tekrar yazılmaları zararsızdır. Yalnızca hesaba özel nihai durum (adım 11: `evaluated_jobs.status`, `report_appearances_count`, Run Log) **tek bir DB transaction'ında** commit edilir. Bu ayrım Section 17'de detaylandırılır.

---

## 9. LinkedIn Toplama (Scraping) Pipeline'ı

**Bileşenler:**
- **SessionManager** — `linkedin_port`'un bir parçası; Playwright'ın `storage_state` (çerezler + local storage) mekanizmasıyla kalıcı oturumu yükler/doğrular. Oturum geçersizse `SessionInvalidError` fırlatır → Orchestrator bunu FR-1 gereği Run'ı "Failed" olarak işaretler ve Run Log'a açıkça yazar.
- **SearchClient** — Config'teki Target Location(s) + geniş rol anahtar kelimeleri kombinasyonlarıyla arama sayfalarını gezer.
- **PaginationController** — FR-21'deki Max Jobs/Pages per Run sınırına ulaşana kadar sayfalar arasında ilerler; sınıra ulaşıldığında toplamayı durdurur ve `collection_capped=true` bayrağını Run Log'a yazar.
- **RecordExtractor** — her ilan kartından FR-2'nin minimum alan setini (başlık, şirket, lokasyon, tarih, açıklama, link) çıkarır; tek bir kaydın ayrıştırma hatası `PartialRecordError` olarak yakalanır ve **o kayıt atlanarak** akış devam eder (FR-2 kabul kriteri) — çalıştırmayı durdurmaz.
- **RateLimiter** — istekler arası konfigüre edilebilir gecikme + jitter uygular (bkz. Section 22); tek oturum, paralel tarayıcı sekmesi yoktur.

**Anomali tespiti (RISK-2):** Bir çalıştırmada toplanan ilan sayısı, son N çalıştırmanın ortalamasından belirgin şekilde düşükse (örn. "sıfır sonuç" veya konfigüre edilebilir bir eşiğin altı), Collection Service bunu bir `LowYieldWarning` olarak loglar (Run'ı başarısız yapmaz, ama görünür bir uyarı üretir) — RISK-2'nin "sessiz veri kaybı" senaryosuna karşı erken sinyal.

**Kapsam dışı bırakılan konu:** Bu belge, LinkedIn'in bot-tespit mekanizmalarını atlatmaya yönelik teknikler (tarayıcı parmak izi sahteciliği vb.) içermez. RISK-1 mitigasyonu, PRD'nin zaten onayladığı ölçüde kalır: muhafazakâr istek hızı, zamanlama sapması (jitter), tek oturum tekrar kullanımı — bunlar "iyi bot vatandaşlığı" pratikleridir, aktif tespit-atlatma mühendisliği değildir.

---

## 10. AI Değerlendirme Pipeline'ı

**LLM Gateway'in dört mantıksal çağrı türü:**

| Çağrı Türü | Ne Zaman Çalışır | Model Kademesi | Gerekçe |
|---|---|---|---|
| Department Relevance Confidence (FR-4) | Location+Experience filtrelerini geçen her ilan için | Hızlı/ucuz kademe | Section 11.4'ün "AI çağrısını en son, en ucuz filtrelerden sonra çalıştır" ilkesi; yüksek hacim, düşük karmaşıklık görev |
| Experience Level Inference (FR-5, EDGE-1) | Yalnızca seviye açıkça etiketlenmemişse | Hızlı/ucuz kademe | Aynı gerekçe — sık çalışan, basit sınıflandırma görevi |
| Company Scoring Assistance (Section 12) | Yalnızca cache miss durumunda (Section 12.4) | Orta kademe | Önbellekleme sayesinde nadiren çalışır; kalite/maliyet dengesi orta kademeyi haklı çıkarır |
| AI Match Rationale Generation (Section 13, FR-7) | Yalnızca cache miss durumunda (FR-18) | Yüksek kaliteli kademe | Açıklanabilirlik (RISK-10 mitigasyonu) burada en kritik; nadiren çalıştığı için yüksek kaliteli model maliyeti düşüktür |

**Kritik tasarım kararı — "LLM sinyal çıkarır, kod skoru hesaplar" (NFR-12'nin mekanik çözümü):** LLM'den hiçbir zaman doğrudan "0-100 nihai skor" istenmez. Bunun yerine LLM, yapılandırılmış **alt-sinyaller** üretir (örn. department confidence: 0.0-1.0, experience match: boolean + gerekçe, career goal alignment: 0.0-1.0 + kısa açıklama). Nihai ağırlıklı toplam (Section 12.1 / 13.1 formülleri), bu sinyaller ve Config'teki ağırlıklar üzerinden **kod içinde deterministik olarak** hesaplanır.
**Gerekçe:** PRD incelemesinde NFR-12 (skor tutarlılığı) ile LLM'in olasılıksal doğası arasındaki gerilim tespit edilmişti. Bu tasarım, aritmetiği (deterministik) olasılıksal kısımdan (sinyal çıkarımı) ayırır; aynı girdiyle aritmetik her zaman aynı sonucu verir, ve sinyal çıkarımı zaten önbellekleme (FR-18) sayesinde içerik değişmedikçe tekrar çalışmaz. Ayrıca "Unrated şirket → ağırlık yeniden normalize et" (Section 12.3) gibi kuralları kod içinde test edilebilir, denetlenebilir hale getirir.

**Grounding zorunluluğu (RISK-10 mitigasyonu, mekanik uygulama):** AI Match Rationale prompt'u, LLM'e yalnızca hesaplanmış alt-sinyalleri ve bunların açıklamalarını girdi olarak verir — ham iş ilanı metnini serbestçe yorumlamasına izin vermez. Çıktı, yapılandırılmış bir şema ile (her madde `{component, value, explanation}` şeklinde) doğrulanır; şemaya uymayan veya sinyal setinde karşılığı olmayan bir madde üretilirse **tek bir "repair" yeniden istemi** denenir, yine başarısız olursa o ilanın AI Match Score'u **tahmin üretmek yerine** "Scoring Unavailable" olarak işaretlenir (bkz. Section 21).

**Prompt yönetimi:** Tüm prompt şablonları `config/prompts/` altında versiyonlanmış Markdown dosyaları olarak tutulur (kod içine gömülmez — Section 17.1'in bir uzantısı). Bir prompt şablonu değiştiğinde `ConfigVersion` artar (NFR-12'nin gerektirdiği izlenebilirlik).

---

## 11. Filtreleme Pipeline'ı

**Zincir sırası (PRD Section 11.4'ün TDD seviyesinde inceltilmesi):**

**Blacklist (FR-19) → Location (FR-3) → Experience Level (FR-5) → Department Relevance (FR-4, semantik/LLM).**

**Gerekçe (Blacklist'in en başa eklenmesi):** PRD Section 11.4 yalnızca Location→Experience→Department sırasını tanımlıyordu; Blacklist kontrolü saf bir konfigürasyon-lookup işlemidir (LLM veya karmaşık hesaplama gerektirmez), dolayısıyla maliyet-sıralı filtreleme ilkesinin (Section 11.4'ün kendi gerekçesi) doğal bir uzantısı olarak en ucuz kontrol en başa alınır.

**Her filtre bir `FilterResult` döndürür** (yalnızca boolean değil): `{passed: bool, reason: str, confidence: float | None}`. Bu, Section 15.4'teki `Filter Result Detail` alanının doğrudan kaynağıdır ve açıklanabilirlik (G-3) için gereklidir.

**Experience Level filtresi iki katmanlıdır:** önce kural tabanlı regex/anahtar kelime kontrolü (ucuz, LLM gerektirmez); yalnızca sonuç belirsizse (EDGE-1) LLM tabanlı çıkarıma düşer. Başlık/açıklama çelişkisi durumunda açıklama metni esas alınır (FR-5, EDGE-12) — bu kural, kod seviyesinde "açıklama sinyali > başlık sinyali" öncelik kuralı olarak sabitlenir.

**Borderline mantığı (FR-16):** Filtreleme aşaması reddetmez, `Filtering Pipeline` çıktısı üç değerden birini taşır: `passed`, `rejected`, `borderline`. Borderline durumu yalnızca AI Match Score aşamasında (eşiğin 5 puan altı, Section 17'deki Borderline Bant Genişliği) hesaplanabildiği için, filtreleme aşaması kendi seviyesinde "rejected" kararını yalnızca Location/Experience/Blacklist için kesin verir; Department Relevance güven skoru eşiğe yakınsa (config'teki dept confidence threshold ±bir tolerans) ilan yine de bir sonraki aşamaya (Company/AI Scoring) borderline bayrağıyla ilerler — böylece AI Match Score borderline hesaplaması için gerekli veriye sahip olur.

---

## 12. Zamanlama Mimarisi

**Bileşenler:**
- **`SchedulerPort`** (arayüz) — `schedule_next_run(account_id, interval, jitter_window)`, `cancel(account_id)` gibi işlemleri soyutlar.
- **`APSchedulerAdapter`** — V1 uygulaması; süreç içinde çalışan bir zamanlayıcı, her hesap için (V1'de tek hesap) bir sonraki çalıştırma zamanını `next_run_at = last_run_at + interval_days ± random(jitter_window)` olarak hesaplar (NFR-14).
- **`RunLock`** — DB'deki `run_locks` tablosunda hesap başına tek satır; bir çalıştırma başlarken satır kilitlenir (`locked_at`, `lock_owner`), bitince serbest bırakılır. Hem otomatik hem manuel tetikleme aynı kilidi kontrol eder (Section 14 çakışma önleme, FR-12).
- **Kalıcılık:** `next_run_at`, `accounts` tablosunda saklanır (bkz. Section 15) — yalnızca bellekte değil; süreç yeniden başlatıldığında çizelge kaybolmaz (NFR-2 Reliability'yi destekler).

**Manuel tetikleme akışı:** CLI komutu (`linkedinbot run --account <id>` veya V1'de argümansız) doğrudan `RunLock`'u kontrol eder; kilit doluysa kullanıcıya açık bir "zaten çalışıyor" mesajıyla çıkar (FR-12 kabul kriteri) — otomatik çizelgeyi hiçbir şekilde değiştirmez veya sıfırlamaz.

**Gerekçe (in-process scheduler seçimi):** V1'in tek hesabı ve düşük çalıştırma sıklığı (2 günde bir) için ayrı bir mesaj kuyruğu altyapısı (Celery/Redis) operasyonel karmaşıklığı haklı çıkarmaz. `SchedulerPort` soyutlaması, bu kararın SaaS fazında (çok hesap, bağımsız çizelgeler) maliyetsiz şekilde değiştirilebilmesini sağlar (bkz. Section 28).

---

## 13. Konfigürasyon Mimarisi

**Üç konfigürasyon kategorisi, üç farklı yaşam döngüsü:**

1. **Altyapı konfigürasyonu** (DB bağlantı dizesi, log seviyesi, ortam adı) — ortam değişkenleri (`.env`) üzerinden, süreç başlangıcında bir kez okunur. **Asla** iş kuralı içermez.
2. **Secrets** (LLM API anahtarı, LinkedIn oturum referansı) — `SecretsProvider` üzerinden (bkz. Section 24). **Asla** düz metin config dosyasında veya DB'de saklanmaz.
3. **Hesap/iş konfigürasyonu** (eşikler, ağırlıklar, departman listesi, çizelge, bildirim ayarları, rapor formatı, prompt referansları — PRD Section 17 + 17.1'in tamamı) — DB'deki `account_config_profiles` tablosunda, hesap başına versiyonlanmış satırlar olarak saklanır; ilk tohumlama `config/system.defaults.yaml` + `config/accounts/*.yaml` dosyalarından yapılır.

**Neden hesap konfigürasyonu dosya değil DB'de tutulur:** V1'de tek hesap olsa da, konfigürasyon Section 15.5'teki `Config Snapshot Reference` gereksinimi nedeniyle **versiyonlanabilir ve sorgulanabilir** olmalıdır (hangi rapor hangi config versiyonuyla üretildi). Bir YAML dosyası bunu doğal olarak sağlamaz; DB satırı + `config_version` sütunu sağlar.

**Config/İş Mantığı ayrımının kod seviyesi garantisi:** `filtering`, `scoring`, `reporting` modüllerinin hiçbiri sabit (hardcoded) bir eşik, ağırlık veya departman adı içermez — bunların tümü fonksiyon/metot imzalarında `Config` nesnesi olarak parametre geçirilir. Bu kural, kod incelemesinde (code review) ve isteğe bağlı statik analiz kurallarıyla denetlenir.

---

## 14. Multi-User Hazır Mimari

Bu bölüm, PRD NFR-15 / Section 15.0 / Section 17.1'in somut teknik karşılığıdır.

- **`AccountContext` merkezi soyutlaması:** Run Orchestrator'ın girdisi her zaman bir `AccountContext` nesnesidir (`account_id` + çözümlenmiş `AccountConfigProfile` + `UserProfile`). Hiçbir servis metodu "örtük/global kullanıcı" varsayımıyla çalışmaz — bu, PRD'deki "kullanıcı izolasyonu ilkesi"nin (Section 17.1) kod seviyesindeki zorunlu kılınmasıdır.
- **Account-Scoped tablo kuralı:** `evaluated_jobs`, `reports`, `run_logs`, `account_config_profiles`, `linkedin_sessions`, `user_profiles`, `run_locks` tabloları her zaman bir `account_id` sütunu taşır (V1'de tek değer alır, ama şemadan asla çıkarılmaz). Bu tabloların repository katmanındaki **hiçbir sorgu metodu** `account_id` parametresi olmadan çağrılamaz (imza seviyesinde zorunlu).
- **Shared/Reference tablo kuralı:** `job_postings` ve `companies` tabloları `account_id` taşımaz — bunlar gerçek dünyadaki ilana/şirkete aittir ve hesaplar arası paylaşılır (Section 15.0). `company_scores` tablosu bu iki dünya arasında köprüdür: `weight_profile_id = NULL` olan satırlar paylaşılabilir (sistem varsayılan ağırlıkla hesaplanmış), `weight_profile_id` dolu satırlar hesaba özeldir (Section 12.4).
- **İkinci hesap eklemenin somut maliyeti (V1 mimarisiyle):** `accounts` tablosuna bir satır + `user_profiles`/`account_config_profiles`/`linkedin_sessions` için tohum satırları eklemek. Orchestrator, Filtering, Scoring, Reporting kodlarının **hiçbiri** değişmez — yalnızca Scheduler/CLI katmanı artık birden fazla `AccountContext` üzerinde döner.
- **Bilinen açık nokta (gelecek çalışma için işaretlendi, V1 kapsamında çözülmez):** Her hesabın kendi LinkedIn oturumunu bağlaması (tenant-per-LinkedIn-account modeli), her hesap için ayrı ToS/rate-limit riski yönetimi gerektirir — bu, SaaS geçişinin en büyük bilinmeyenidir ve Section 28'de ayrıca ele alınır.

---

## 15. Veritabanı Tasarımı ve Şema

Aşağıdaki tablolar kavramsal şema düzeyindedir (somut SQL değil); tip adları jenerik olarak verilmiştir.

**Account-Scoped tablolar:**

| Tablo | Anahtar Alanlar | Notlar |
|---|---|---|
| `accounts` | `account_id` (UUID, PK), `display_name`, `created_at`, `status`, `next_run_at` (TIMESTAMP) | V1'de tek satır; `next_run_at` Section 12'deki zamanlama hesaplamasının (interval + jitter) kalıcı karşılığıdır |
| `user_profiles` | `account_id` (PK/FK), `career_goals` (TEXT), `skills_summary` (TEXT), `preferences_dealbreakers` (JSONB — blacklist dahil, FR-19) | PRD 15.1 (Target Departments/Locations/Experience Levels artık `account_config_profiles.target_criteria` içinde versiyonlanır — bkz. PRD Section 15.1 versiyonlama notu) |
| `account_config_profiles` | `account_id` (FK), `config_version` (INTEGER), composite PK (`account_id`,`config_version`) — `target_criteria` (JSONB: departments, locations, experience_levels), `weights_ai_match` (JSONB), `weights_company_quality` (JSONB), `thresholds` (JSONB: cqs, ams, dept_confidence, borderline_band), `schedule` (JSONB: interval_days, jitter_minutes), `collection_limits` (JSONB: max_jobs_per_run), `notification_settings` (JSONB), `report_format_settings` (JSONB), `prompt_template_refs` (JSONB), `is_active` (BOOLEAN), `validated_at` | PRD Section 17 + 17.1; Target Departments/Locations/Experience Levels burada versiyonlanır (bkz. PRD Section 15.1) böylece Config Snapshot bu alanları da kapsar |
| `linkedin_sessions` | `account_id` (PK/FK), `encrypted_storage_state_ref` (TEXT — Secrets Provider'a referans, ham veri değil), `session_status` (ENUM: valid/expired/unknown), `last_validated_at` | FR-1 |
| `evaluated_jobs` | `id` (UUID, PK), `account_id` (FK), `job_id` (FK), `company_id` (FK), `ai_match_score` (NUMERIC, NULL), `match_rationale` (JSONB), `department_cluster` (TEXT), `filter_result_detail` (JSONB), `status` (ENUM: New/Seen/Updated/Closed/Borderline/Excluded), `first_seen_at`, `last_seen_at`, `report_appearances_count` (INTEGER), `content_hash_at_evaluation`, `config_version_used` (FK) — UNIQUE(`account_id`,`job_id`) | PRD 15.4 |
| `reports` | `report_id` (UUID, PK), `account_id` (FK), `generated_at`, `included_job_ids` (JSONB), `top_matches` (JSONB), `format` (TEXT), `config_snapshot_ref` (FK → account_config_profiles), `storage_path` (TEXT) | PRD 15.5 |
| `run_logs` | `run_id` (UUID, PK), `account_id` (FK), `trigger_type` (ENUM: Scheduled/Manual), `started_at`, `ended_at`, `status` (ENUM: Success/Partial/Failed), `jobs_collected`, `jobs_filtered`, `jobs_new`, `jobs_closed` (INTEGER), `error_detail` (TEXT, NULL), `collection_capped` (BOOLEAN) | PRD 15.6 |
| `run_locks` | `account_id` (PK/FK), `locked_at`, `lock_owner`, `lock_expires_at` (TIMESTAMP) | Section 14 çakışma önleme; `lock_expires_at` Section 17'deki kilit zaman aşımı davranışının kalıcı karşılığıdır |

**Shared/Reference tablolar:**

| Tablo | Anahtar Alanlar | Notlar |
|---|---|---|
| `companies` | `company_id` (PK), `name`, `industry`, `employee_count_range`, `founded_year`, `first_seen_at`, `last_updated_at` | PRD 15.3 (hesap taşımaz) |
| `company_scores` | composite PK (`company_id`, `weight_profile_id`, `rubric_version`) — `weight_profile_id` NULL = sistem varsayılanı; `rubric_version`: sistem varsayılanı için sistem geneli paylaşılan sürüm, hesaba özel ağırlık için o hesabın `config_version`'ı; `score_total` (NUMERIC, NULL = Unrated), `score_breakdown` (JSONB), `evaluated_at` | Section 12.4 çok-kullanıcılı önbellekleme kuralı — `rubric_version`, puanlama mantığı (ağırlık/prompt) değiştiğinde eski skorların yanlışlıkla yeniden kullanılmasını engeller |
| `job_postings` | `job_id` (PK, LinkedIn native ID), `title`, `company_id` (FK), `location_text`, `workplace_type` (ENUM), `posted_date`, `description` (TEXT), `employment_type`, `easy_apply` (BOOLEAN), `application_url`, `collected_at`, `content_hash` | PRD 15.2 (hesap taşımaz); `content_hash` yalnızca Title/Experience Level/Location/Workplace Type/Description alanlarından hesaplanır (bkz. Section 6, FR-14) |

**Önerilen indeksler (V1'den itibaren, ölçek için — bkz. Section 28):** `evaluated_jobs(account_id, status)`, `evaluated_jobs(job_id, account_id)`, `job_postings(content_hash)`, `company_scores(company_id, weight_profile_id)`, `run_logs(account_id, started_at)`.

**Rubric Version kaynağı:** Sistem varsayılanı için Rubric Version, `config/system.defaults.yaml` ve `config/prompts/company_scoring.prompt.md` dosyalarının birleşik, sistem geneli bir sayaçtan türeyen sürüm numarasıdır (bu dosyalardan biri değiştiğinde artar); hesaba özel ağırlık profilleri için doğrudan o hesabın `account_config_profiles.config_version` değeridir. Bu, FR-18'in Job-seviyesi önbellek anahtarındaki (`Job ID + Account ID + Config Version`) versiyon mantığıyla tutarlıdır — iki önbellek de aynı prensiple (mantık değişince anahtar değişir) çalışır, yalnızca sistem-varsayılanı durumunda paylaşım için hesap-bağımsız bir sürüm kullanılır.

**Gerekçe (JSONB kullanımı):** Ağırlıklar, eşikler ve gerekçe maddeleri gibi alanlar PRD'nin kendisinde bile evrilmeye açık olarak tanımlanmış (Section 17 "yeni parametre eklenmesi" örnekleri). JSONB, şema migration'ı gerektirmeden yeni bir ağırlık bileşeni veya config alanı eklenmesine izin verir; sabit sütunlu bir tasarım her yeni parametre için bir migration'a zorlar (NFR-8'e aykırı olurdu).

---

## 16. Varlık İlişkileri (ER)

```
accounts (1) ──── (1) user_profiles
accounts (1) ──── (N) account_config_profiles   [tam olarak bir tanesi is_active=true]
accounts (1) ──── (1) linkedin_sessions
accounts (1) ──── (1) run_locks
accounts (1) ──── (N) evaluated_jobs
accounts (1) ──── (N) reports
accounts (1) ──── (N) run_logs
run_logs (1) ──── (1) reports                   [her Run tam olarak bir Report üretir — bkz. PRD Section 15.7]

companies (1) ──── (N) job_postings
companies (1) ──── (N) company_scores

job_postings (1) ──── (N) evaluated_jobs      ⟵ bkz. not aşağıda
account_config_profiles (1) ──── (N) reports          [config_snapshot_ref üzerinden]
account_config_profiles (1) ──── (N) company_scores   [weight_profile_id üzerinden, yalnızca özelleştirilmiş profiller]
```

**Kasıtlı sapma notu:** PRD Section 15.7, "Job Posting (1) → (1) Evaluated Job" ilişkisini tanımlar (V1'in tek hesaplı dünyasında doğru). Bu TDD, şemayı bilinçli olarak **Job Posting (1) → (N) Evaluated Job** olarak genelleştirir — her hesap aynı paylaşılan ilana kendi `evaluated_jobs` satırıyla sahip olabilir. V1'de tek hesap olduğu için pratikte 1→1 davranır, ancak bu, "büyük bir mimari değişiklik gerektirmeden çok-kullanıcıya evrilme" talimatının doğrudan uygulanmasıdır — şema zaten N'i destekler.

---

## 17. Durum Yönetimi (State Management)

**Job durum makinesi** (`evaluated_jobs.status`): `New → Seen`; `Seen → Updated` (FR-14 anlamlı değişiklik tetiklendiğinde) `→ Seen`; `Seen/Updated → Closed`; `Closed → New` (yeniden açılma, EDGE-5). `Borderline` bağımsız bir bayrak olarak modellenir (bir ilan aynı anda `New` VE `Borderline` olabilir) — durum enum'unun bir kolu değil, ayrı bir boolean alan olarak tutulur (`is_borderline`).

**Run durum makinesi:** `Pending → Running → {Success, Partial, Failed}`. `Running`'e giriş `RunLock` satırının kilitlenmesiyle eşzamanlıdır; terminal duruma ulaşınca kilit serbest bırakılır.

**Atomiklik stratejisi (NFR-13'ün mekanik çözümü) — "eager cache, atomic final state":**
- **Güvenle erken yazılabilir veriler:** `job_postings`, `companies`, `company_scores` (sistem varsayılanı), LLM'den dönen ham sinyaller için ara önbellek kayıtları. Bunlar idempotent ve hesaplar arası paylaşılabilir olduğundan, pipeline ilerledikçe **hemen** DB'ye yazılabilir; bir kesinti durumunda "fazladan" yazılmış olmaları zararsızdır, üstelik bir sonraki çalıştırmanın aynı işi tekrar yapmasını (ve LinkedIn/LLM'e tekrar gitmesini) önler.
- **Yalnızca tek transaction'da commit edilecek veriler:** `evaluated_jobs.status` güncellemeleri, `report_appearances_count` artışları, `reports` satırı, `run_logs` satırı — yani hesaba görünür "nihai" durum. Bunların tamamı Orchestrator'ın son adımında (State Update, PRD adım 11) **tek bir DB transaction'ı** içinde commit edilir.
- **Kesinti senaryosu (EDGE-14):** Süreç, State Update transaction'ı commit edilmeden önce çökerse: cache tabloları (job_postings, company_scores) kısmen güncellenmiş olabilir (zararsız), ancak `evaluated_jobs`/`reports`/`run_logs` **hiç değişmemiş** olur. Bir sonraki çalıştırma, zaten önbelleğe alınmış veriyi yeniden kullanarak (LinkedIn/LLM'e tekrar gitmeden) kaldığı yerden değil, temiz bir çalıştırma olarak başlar — ama önbellek sayesinde bu neredeyse ücretsizdir. `RunLock`, sürecin normal kapanışta serbest bırakamadığı durumlar için `run_locks.lock_expires_at` alanında bir **timeout** taşır (bkz. Section 15) — bu alan aşıldığında kilit otomatik geçersiz sayılır; sonsuza kadar kilitli kalmayı önler.

---

## 18. Rapor Üretim Akışı

1. **Reporting Compiler**, sıralanmış/gruplanmış `EvaluatedJob` listesini ve hesabın önceki `reports` kayıtlarını (Top Matches "Previously Reported" tespiti için — bkz. PRD 16.3) girdi olarak alır.
2. Section 16.2'deki Markdown şablonunu (`reporting/templates/markdown_report.template.md`, config'ten referanslanan `report_format_settings` ile parametrelenebilir) doldurur.
3. **`ReportStore` Port** çağrılır; V1 uygulaması (`FilesystemReportStore`) dosyayı `reports/{account_id}/{YYYY-MM-DD}_{report_id}.md` yoluna yazar (FR-17 — üzerine yazma yok, her çalıştırma kendi dosyasını üretir).
4. `reports` tablosuna satır eklenir: `storage_path`, `config_snapshot_ref` (o anki `account_config_profiles.config_version`), `included_job_ids`, `top_matches`.
5. **İdempotency güvencesi:** Compiler, aynı `run_id` için daha önce bir `reports` satırı var mı diye kontrol eder (RunLock zaten çift çalışmayı engeller, ama bu ikinci bir savunma katmanıdır — Section 21 "Idempotency" ilkesinin somutlaşması).
6. **Bootstrap davranışı (FR-20):** Compiler, hesabın `run_logs` geçmişi boşsa (ilk çalıştırma), şablonun normal "NEW" bölümleri yerine ayrı bir "Bootstrap / İlk Tarama" bölümünü render eder.

**Not (rapor üretiminin koşulsuzluğu):** Orchestrator, hiçbir koşulda rapor üretimini tamamen atlamaz — yeni/güncellenmiş ilan bulunamasa bile Compiler, EDGE-7'de tanımlanan hafif özet raporunu üretir. Bu, PRD Section 15.7'deki Run Log → Report ilişkisinin (1)→(1) olmasının doğrudan karşılığıdır (bkz. Section 16 ER diyagramı).

---

## 19. Loglama Stratejisi

**İki ayrı log hedefi, iki farklı amaç:**

1. **Yapılandırılmış (JSON) dosya logları** — geliştirici/operasyonel hata ayıklama için; her satır `{timestamp, account_id, run_id, stage, level, message, extra}` alanlarını taşır. Yerel diskte döndürülen (rotating) dosyalar olarak tutulur.
2. **`run_logs` DB tablosu** — PRD FR-15/NFR-10'un gerçek "gözlemlenebilirlik sözleşmesi"; yalnızca iş seviyesinde özet (sayılar, durum, hata detayı) içerir, kalıcı ve sorgulanabilirdir.

**Gerekçe (iki katman):** Dosya logları ayrıntılı ama geçicidir (disk alanı sınırlıdır, rotasyona tabidir); DB logu az ayrıntılı ama kalıcı ve sorgulanabilirdir (örn. "son 30 günde kaç Run Failed oldu" sorusu). Bu ikisini birleştirmemek, FR-15'in kalıcılık gereksinimini disk rotasyon politikasından bağımsızlaştırır.

**Log seviyesi eşlemesi:** INFO (aşama sınırları, sayılar) · WARNING (kurtarılabilir anomaliler — düşük verim, EDGE-9 kısmi sonuç) · ERROR (aşamayı durduran hatalar — her ERROR, karşılık gelen `run_logs.error_detail` alanını doldurmak **zorundadır**, bu kural bir test ile denetlenir).

**Secret redaksiyonu:** Structured logger, bilinen secret alan adlarını (API key, session token) otomatik olarak `[REDACTED]` ile değiştiren bir filtre içerir (bkz. Section 24, 26).

---

## 20. Hata Yönetimi Stratejisi

**Hata taksonomisi:**

| Sınıf | Örnek | Davranış |
|---|---|---|
| `TransientError` | Ağ zaman aşımı, LLM 429/5xx, geçici DB bağlantı hatası | Retry mekanizmasına girer (bkz. Section 21) |
| `PermanentError` | Geçersiz oturum (FR-1), şema dışı config (EDGE-15), LinkedIn yapısal değişikliği nedeniyle ayrıştırılamayan sayfa | Retry edilmez; Run "Failed" olarak sonlanır, `error_detail` doldurulur |
| `PartialRecordError` | Tek bir ilan kaydının ayrıştırılamaması (FR-2) | Kayıt atlanır, loglanır, çalıştırma devam eder; Run sonunda "Partial" olabilir |

**Merkezi hata sınıflandırma kuralı:** Her modül yalnızca kendi sınıflandırabileceği hatayı yakalar ve normalize edilmiş bir istisna türü olarak yukarı fırlatır; **yalnızca Run Orchestrator** bu istisnalardan Run'ın nihai durumunu (Success/Partial/Failed) belirler.
**Gerekçe:** Run-sonucu mantığının tek bir yerde toplanması, dağınık ad-hoc durum kararlarını önler ve gelecekte yeni bir durum türü eklemeyi (örn. SaaS fazında "Degraded") tek dosyalık bir değişikliğe indirger (bakım kolaylığı).

---

## 21. Retry Mekanizmaları

- **LinkedIn istekleri:** Üstel geri çekilme (exponential backoff) + jitter, sınırlı deneme sayısı (örn. 3); tükenirse o sayfa/sorgu "başarısız ama devam et" olarak işaretlenir (RISK-2).
- **Devre kesici (circuit-breaker-lite):** Bir çalıştırma içinde ardışık LinkedIn hata sayısı bir eşiği aşarsa, toplama erken sonlandırılır ve Run "Partial" işaretlenir — bozuk bir koşulda saatlerce her isteği tüketene kadar denemeyi önler (RISK-1/RISK-2).
- **LLM çağrıları:** Yalnızca geçici hatalar (zaman aşımı, 5xx, 429) yeniden denenir. Yapısal olarak bozuk/grounding'i sağlamayan çıktı için **tek bir "repair" yeniden istemi** denenir; yine başarısız olursa o ilan "Scoring Unavailable" olarak işaretlenir — sonsuz döngü veya uydurma bir skor **asla** üretilmez (RISK-10'un başarısızlık yoluna genişletilmesi).
- **DB bağlantı hataları:** Kısa, sınırlı sayıda otomatik yeniden bağlanma denemesi (ORM/connection pool seviyesinde standart pratik).

---

## 22. Rate Limiting Stratejisi

- **LinkedIn toplama:** Sabit gecikme + jitter (varsayılan konfigüre edilebilir aralık, örn. istekler arası birkaç saniye), tek eşzamanlı oturum, paralel tarayıcı örneği yok. Bu, PRD RISK-1/NFR-14'ün teknik uygulamasıdır — saldırgan bir hız optimizasyonu değil, muhafazakâr bir varsayılan.
- **LLM çağrıları:** LLM Gateway, sağlayıcının rate-limit başlıklarını okuyup kendi istek hızını buna göre ayarlar (throttle); ayrıca FR-21'deki Max Jobs/Pages per Run sınırından türetilen **yumuşak bir çalıştırma-başı maliyet/çağrı bütçesi** uygulanır — tek bir çalıştırmanın kontrolsüz harcama yapması engellenir (RISK-9).
- **Eşzamanlılık sınırı:** Bir hesap için aynı anda yalnızca bir Run çalışabilir (RunLock); LLM Gateway'in kendi iç eşzamanlılığı da (örn. aynı anda kaç ilan skorlanabilir) konfigüre edilebilir bir üst sınıra sahiptir.

---

## 23. Konfigürasyon Yükleme

**Öncelik zinciri (düşükten yükseğe):**

1. Kod içi güvenli varsayılanlar (yalnızca toplam başlangıç çökmesini önlemek için asgari fallback — iş kuralı içermez).
2. `config/system.defaults.yaml` (PRD Section 17 varsayılanları).
3. `account_config_profiles` DB satırı (`is_active=true` olan en güncel `config_version`) — hesap bazlı geçersiz kılma.
4. Ortam değişkenleri — **yalnızca altyapı** ayarları için (DB URL, log seviyesi); iş kuralı asla env var ile geçersiz kılınmaz (Section 13'teki ayrımın zorunlu kılınması).

**Yükleme zamanlaması:** Config, her Run'ın başında **bir kez** okunup `AccountContext` içine "dondurulur" (snapshot alınır); çalıştırma sırasında config DB'de değişse bile, o çalıştırmanın geri kalanı tutarlı bir görünüm kullanır — bu, tek bir çalıştırma içinde tutarsız davranışı önler (küçük ama önemli bir tutarlılık kararı).

**Doğrulama zamanlaması (FR-13, EDGE-15):** (a) Yazma zamanında — `linkedinbot config validate` komutu veya (gelecekte) bir yönetim API'si, ağırlık toplamlarının %100 olduğunu, referans verilen departman/lokasyon kümelerinin var olduğunu doğrular; (b) Çalıştırma başlangıcında — savunma amaçlı ikinci bir doğrulama, DB'deki config'in yazma sonrası bozulmamış olduğunu garanti eder (fail-fast).

---

## 24. Secrets Yönetimi

**Kapsam:** V1'de yalnızca iki secret sınıfı vardır: (1) LLM sağlayıcı API anahtarı, (2) LinkedIn oturum durumu (Playwright `storage_state`).

**Kritik güvenlik kararı — parola değil, oturum durumu saklanır:** Kullanıcının LinkedIn parolası yalnızca ilk interaktif girişte kullanılır ve **hiçbir zaman diske yazılmaz**; yalnızca giriş sonrası oturum durumu (çerezler/local storage) kalıcı hale getirilir. **Gerekçe:** Bu, sızıntı durumunda maruz kalan bilginin etki alanını daraltır (bir oturum belirteci süresi dolunca veya iptal edilince değersizleşir; bir parola değersizleşmez).

**Saklama mekanizması:** `SecretsProvider` Port; V1 uygulaması (`LocalKeyringSecretsProvider`) verileri simetrik şifreleme (anahtar OS keychain'den veya kaynak koduna asla girmeyen bir ortam değişkeninden alınır) ile diskte şifreli tutar.
**Gerekçe:** Tek makineli kişisel dağıtım için barındırılan bir secrets servisi (Vault, AWS Secrets Manager) aşırı mühendisliktir; ama arayüz soyutlaması sayesinde SaaS fazında bu adaptör değiştirilebilir (bkz. Section 2, 27).

**Erişim kuralı:** Hiçbir modül `SecretsProvider`'ı bypass edip secrets'a doğrudan dosya/env okuyarak erişemez; tüm erişim `secrets_provider_port.get(key)` üzerinden geçer — bu, Section 19'daki log-redaksiyon filtresiyle birlikte, bir secret'ın yanlışlıkla loglanma riskini azaltır.

---

## 25. Harici Entegrasyonlar

| Entegrasyon | Durum (V1) | Mekanizma |
|---|---|---|
| LinkedIn | Aktif | Playwright ile oturum tabanlı tarayıcı otomasyonu (resmi bir genel API bu kullanım senaryosunu desteklemez) |
| LLM Sağlayıcı (Anthropic) | Aktif | `LLMProvider` Port arkasında REST/SDK çağrısı |
| Notification (Email/Telegram/Discord/Slack) | **Pasif — arayüz ayrılmış** | `NotificationProviderPort` tanımlı, V1'de yalnızca `NoOpNotificationAdapter` bağlı; Phase 2'de somut adaptörler eklenecek (kod değişikliği yalnızca yeni adaptör dosyası, çekirdek dokunulmaz) |
| Ek çıktı entegrasyonları (Notion/Sheets/Airtable) | **Pasif — arayüz ayrılmış** | `ReportStore`/gelecekteki `OutputSinkPort` genişletme noktası (Phase 2) |

**Gerekçe (Notification/Output için "boş ama tanımlı" arayüz):** PRD Section 17.1 açıkça "V1'de kullanılmasa da konfigürasyon şeması Phase 2 için şimdiden ayrılır" diyor. Bu, o gereksinimin kod seviyesi karşılığıdır — Phase 2 geldiğinde yeni bir alt sistem inşa etmek yerine, zaten var olan bir yuvaya somut bir adaptör takılır.

---

## 26. Güvenlik Değerlendirmeleri

- **Kimlik bilgisi maruziyetinin en aza indirilmesi:** Bkz. Section 24 (parola değil, oturum durumu).
- **Log redaksiyonu:** Bilinen secret alan adları hiçbir zaman loglanmaz (Section 19).
- **Prompt injection farkındalığı:** İş ilanı açıklamaları **güvenilmeyen dış girdidir** (açık bir platformdan toplanır). LLM Gateway, prompt şablonlarında "veri" ile "talimat" alanlarını açıkça ayırır (yapılandırılmış slotlar) ve ilan açıklaması içeriğinin skorlama talimatlarını değiştirebileceği bir prompt tasarımından kaçınılır — kötü niyetli bir ilan metninin skorlama mantığını manipüle etme riskini azaltır.
- **En az yetki (least privilege) DB erişimi:** Uygulama, superuser değil, yalnızca gerekli tablolara CRUD yetkisi olan bir DB kullanıcısıyla bağlanır; tüm sorgular ORM üzerinden parametrize edilir (ham string SQL yok) — enjeksiyon riski yapısal olarak elenir.
- **Çok-kiracılı izolasyon (ileriye dönük sertleştirme):** V1'de `account_id` filtrelemesi yalnızca uygulama/repository katmanında zorunlu kılınır. SaaS lansmanından **önce** bir gereksinim: Postgres **Row-Level Security (RLS)** politikalarının eklenmesi, uygulama katmanındaki olası bir hatanın hesaplar arası veri sızıntısına yol açmasına karşı savunma derinliği sağlar. V1'de tek hesap olduğu için bu bir blocker değildir, ama SaaS öncesi kontrol listesine açıkça eklenir.
- **Bağımlılık hijyeni:** Kilitli (pinned) bağımlılık sürümleri, düzenli güvenlik güncellemesi taraması (standart pratik, burada sadece not edilir).

---

## 27. Dağıtım Mimarisi

**V1 — Tek host, Docker Compose:**
- İki konteyner: `app` (Python süreci — scheduler döngüsü + CLI) ve `db` (PostgreSQL).
- Kalıcı volume'lar: Postgres veri dizini, şifreli secrets deposu, rapor çıktı dizini (konteyner dışında, host üzerinde kalıcı).
- Konfigürasyon/secrets `.env` (git'e eklenmez) ve mount edilmiş `config/` dizini üzerinden enjekte edilir.
- Çalışma ortamı: kullanıcının kendi her zaman açık makinesi veya küçük bir VPS.

**Yedekleme:** Zamanlanmış `pg_dump` ile Postgres'in düzenli olarak ayrı bir depolama konumuna yedeklenmesi (örn. günlük cron görevi).
**Gerekçe:** PRD NFR-11 (asla silme) ve RISK-7 (Single Point of Failure) göz önüne alındığında, tam yüksek erişilebilirlik (HA) V1 için orantısız olsa da, düzenli yedekleme neredeyse sıfır maliyetli asgari bir mitigasyondur — PRD incelemesinde tespit edilen "yedekleme/kurtarma gereksinimi yok" boşluğunu kapatır.

**Gelecek SaaS dağıtım taslağı (yalnızca yön, detaylandırılmamış):** Konteynerler → Kubernetes/ECS üzerinde, tüm hesaplara hizmet veren paylaşımlı bir `app` deployment'ı (iş mantığı zaten hesap-parametrik olduğu için); yönetilen Postgres (RDS/Cloud SQL) + RLS; secrets bulut KMS/secrets manager'a taşınır; Scheduler, in-process APScheduler'dan dağıtık bir iş kuyruğuna (Celery/RQ + Redis veya yönetilen bir zamanlayıcı) geçer; hesap/config yönetimi için yeni bir web kontrol düzlemi (örn. FastAPI) **yeni bir adaptör olarak** eklenir. **Bu geçişin hiçbiri domain/pipeline modüllerinin yeniden yazılmasını gerektirmez** — yalnızca Section 1'de tanımlanan Port'ların arkasındaki adaptörler değişir.

---

## 28. Ölçeklenebilirlik Değerlendirmeleri

- **En büyük bilinmeyen — hesap başına LinkedIn oturumu:** Çok-kiracılı bir gelecekte her hesabın kendi LinkedIn oturumunu bağlaması gerekir; bu, her hesap için ayrı ToS/rate-limit riski taşır (RISK-1'in çarpanlı hali) ve V1 mimarisinin çözmediği, bilinçli olarak açık bırakılmış bir sorudur (bkz. Section 14 "bilinen açık nokta").
- **Paylaşılan referans verinin ölçek kazanımı:** `job_postings`/`company_scores` (varsayılan ağırlıkla) tablolarının hesaplar arası paylaşılması, örtüşen arama kapsamına sahip birden fazla hesabın aynı ilanı/şirketi tekrar tekrar taramasını/puanlamasını **daha en baştan** önler — bu, şemanın ilk günden itibaren sağladığı somut bir ölçek kazanımıdır (rastgele bir optimizasyon değil, Section 15.0'ın tasarım sonucu).
- **İndeksleme:** Veri hacmi arttıkça (`evaluated_jobs`, `run_logs`, `job_postings`) sorgu performansı için Section 15'te listelenen indeksler V1'den itibaren uygulanmalıdır — sonradan eklemek canlı bir sistemde daha maliyetlidir.
- **Yatay ölçekleme yolu:** Run Orchestrator, `AccountContext` dışında paylaşılan bellek-içi durum taşımadığı (RunLock DB tabanlıdır, bellekte değil) için, birden fazla hesabın çalıştırmaları zaten ayrı worker süreçlerinde **eşzamanlı** yürütülebilir — mimari yeniden tasarım gerektirmeden. Bu, hesap-parametrik çekirdek kararının (Section 1, Karar 3) somut ölçek kanıtıdır.

---

## 29. Gelecek Genişletilebilirlik Değerlendirmeleri

PRD Section 18'deki her roadmap özelliğinin, bu mimaride hangi genişletme noktasını kullanacağı:

| PRD Roadmap Özelliği | Genişletme Noktası | Neden Çekirdek Değişmez |
|---|---|---|
| AI Job Summary / Company Intelligence | LLM Gateway'e yeni bir prompt türü + `job_postings`/`companies` üzerinde yeni bir alan | Mevcut LLM Gateway ve şema zaten genişletilebilir (JSONB) |
| Personal Dashboard | `run_logs`/`evaluated_jobs` üzerinde salt-okunur yeni bir agregasyon servisi | Veri zaten NFR-11 gereği hiç silinmeden tutulduğu için yeni bir şema gerekmez |
| Notification System | `NotificationProviderPort`'un somut adaptörleri (Email/Telegram/Discord/Slack) | Arayüz zaten V1'de ayrılmış (Section 25) |
| Ek çıktı entegrasyonları (Notion/Sheets) | `ReportStore`/yeni `OutputSinkPort` adaptörleri | `ReportStore` zaten bir Port; yeni adaptör eklemek mevcut akışı bozmaz |
| CV Optimization / Cover Letter / Automatic Easy Apply | Yeni bir sınırlı bağlam (bounded context) modülü (`applications/`), `evaluated_jobs`'u okur ama keşif pipeline'ını değiştirmez | Modüler monolit + Hexagonal sınırlar, yeni bir bağlamın mevcut pipeline'a müdahale etmeden eklenmesine izin verir |
| Application Tracker | Yeni bir Account-Scoped tablo + modül | Şema zaten Account-Scoped/Shared ayrımını takip ediyor; yeni tablo ekleme, mevcut tabloları değiştirmeden yapılabilir |
| AI Career Advisor / Interview Prep / Career Trend Analysis | Yeni analiz servisleri, birikmiş geçmiş veri (NFR-11) üzerinde çalışır | Veri temeli zaten Phase 4 için yeterli geçmişi taşıyacak şekilde tasarlandı (Section 15) |

Bu tablo, PRD'nin G-8 (Genişletilebilir mimari) ve NFR-8 hedeflerinin somut, doğrulanabilir bir kanıtı olarak işlev görür.

---

## Appendix A: Gereksinim → Bileşen İzlenebilirlik Matrisi

| PRD Kimliği | Gereksinim (özet) | Sorumlu TDD Bileşeni |
|---|---|---|
| FR-1 | Session validation + görünür hata | `adapters.linkedin.session_manager`, Section 20 |
| FR-2 | Toplama, tek kayıt hatası çalıştırmayı durdurmaz | `collection.collector`, `PartialRecordError` |
| FR-3/FR-5/FR-4 | Location/Experience/Department filtreleri | `filtering/*`, Section 11 |
| FR-6/FR-18 | Company/Score caching | `scoring.score_cache`, Section 12.4 |
| FR-7 | AI Match Score + grounded rationale | `scoring.ai_matching`, LLM Gateway, Section 10 |
| FR-8/FR-9/FR-10/FR-14 | Duplicate/New/Closed/Updated tespiti | `history.diff_engine`, `history.content_hasher` |
| FR-11 | Rapor üretimi | `reporting.compiler`, Section 18 |
| FR-12 | Zamanlama + çakışma önleme | `run.run_lock`, `adapters.scheduling` |
| FR-13 | Config yönetimi + doğrulama | `config.loader`, `config.validator` |
| FR-15 | Run Log | `db.repositories.run_log_repository` |
| FR-16 | Borderline bucket | `filtering.pipeline`, `scoring.ai_matching` |
| FR-17 | Kalıcı rapor dosyası | `adapters.reporting.filesystem_report_store` |
| FR-19 | Blacklist | `filtering.blacklist_filter` |
| FR-20 | Bootstrap/cold-start | `reporting.compiler` |
| FR-21 | Toplama hacmi sınırı | `collection.collector` (PaginationController) |
| NFR-1/NFR-2 | Performans/Güvenilirlik | Section 21, 22 (retry/rate limit) |
| NFR-3/NFR-4 | Güvenlik/Uyum farkındalığı | Section 24, 26 |
| NFR-6/NFR-8 | Konfigürasyon/Genişletilebilirlik | Section 13, 29 |
| NFR-9 | Maliyet verimliliği | Section 10 (model kademelendirme), 22 |
| NFR-12 | Skor tutarlılığı | Section 10 ("LLM sinyal çıkarır, kod hesaplar") |
| NFR-13 | Run atomikliği | Section 17 |
| NFR-14 | Jitter | `adapters.scheduling`, Section 12 |
| NFR-15 | Multi-Tenancy Readiness | Section 14 (bütünüyle) |
| RISK-1/RISK-2 | Platform/veri güvenilirliği | Section 9, 22 |
| RISK-7 | SPOF | Section 27 (yedekleme) |
| RISK-9 | Maliyet artışı | Section 10, 22 |
| RISK-10 | AI Hallucination | Section 10 (grounding), Section 21 |
| EDGE-14 | Yarıda kesilen çalıştırma | Section 17 (atomiklik stratejisi) |
| EDGE-15 | Geçersiz config | Section 23 (doğrulama) |

---

## Appendix B: Teknik Sözlük

| Terim | Tanım |
|---|---|
| Port | Çekirdek iş mantığının dış dünyaya bağımlılığını soyutlayan arayüz (örn. `LLMProviderPort`) |
| Adapter | Bir Port'un somut, teknolojiye özgü uygulaması (örn. `AnthropicLLMAdapter`) |
| Hexagonal Architecture (Ports & Adapters) | Çekirdeğin yalnızca soyut arayüzlere bağımlı olduğu, somut teknolojilerin dışarıda tutulduğu mimari yaklaşım |
| AccountContext | Bir çalıştırmanın hangi hesap için, hangi çözümlenmiş konfigürasyonla yürütüldüğünü taşıyan nesne |
| Content Hash | Bir ilanın yalnızca Title, Experience Level, Location, Workplace Type ve Description alanlarından türetilen özet değeri (görüntülenme sayısı gibi oynak alanlar hariç); değişiklik tespiti (FR-14) ve önbellekleme (FR-18) için kullanılır |
| Weight Profile ID | Company/AI skor ağırlıklarının belirli bir kümesini tanımlayan kimlik; `NULL` sistem varsayılanını ifade eder |
| Rubric Version | Puanlama mantığının (ağırlıklar veya ilgili prompt şablonu) hangi sürümüyle hesaplandığını belirten sayaç; sistem varsayılanı için sistem geneli, hesaba özel ağırlık için hesabın kendi `config_version`'ı kullanılır (bkz. Section 12.4, Section 15) |
| RunLock | Bir hesap için aynı anda yalnızca bir çalıştırmanın ilerlemesini garanti eden DB tabanlı kilit mekanizması |
| Eager Cache / Atomic Final State | Paylaşılabilir ara verinin hemen yazılıp, hesaba özel nihai durumun tek transaction'da commit edildiği durum yönetimi deseni |
| Structured Signal Extraction | LLM'in nihai sayısal skoru değil, ağırlıklandırılmış formülün girdisi olan alt-sinyalleri ürettiği tasarım deseni |

---

## Appendix C: Version History

| Versiyon | Tarih | Değişiklik |
|---|---|---|
| 1.0 | 2026-08-07 | İlk Technical Design Document oluşturuldu; PRD v1.2'nin tüm Must-have/Should-have gereksinimleri, NFR-15 (Multi-Tenancy Readiness) dahil, somut mimari kararlara ve bileşenlere eşlendi. |
| 1.1 | 2026-08-07 | PRD v1.3 ile birlikte, ortak mimari incelemede tespit edilen 5 tutarsızlık çözüldü (yeni bileşen veya kapsam değişikliği yok): (1) Section 16 ER diyagramına `run_logs (1)→(1) reports` ilişkisi eklendi, Section 18'e rapor üretiminin hiçbir koşulda atlanmadığını belirten bir not eklendi; (2) Section 15 şemasında `target_departments`/`target_locations`/`target_experience_levels` alanları `user_profiles`'tan `account_config_profiles.target_criteria`'ya taşındı, böylece Config Snapshot bu alanları da kapsıyor; (3) `company_scores` önbellek anahtarına `rubric_version` eklendi (sistem varsayılanı için sistem geneli sürüm, hesaba özel ağırlık için hesabın `config_version`'ı), ilgili Section 6 modül satırı ve Appendix B güncellendi; (4) `content_hash`'in yalnızca FR-14 kapsamındaki alanlardan (Title/Experience Level/Location/Workplace Type/Description) hesaplandığı Section 6, Section 15 ve Appendix B'de netleştirildi; (5) `accounts` tablosuna `next_run_at`, `run_locks` tablosuna `lock_expires_at` alanları eklendi ve Section 12/Section 17'nin bu alanlara açıkça atıf yapması sağlandı. |
