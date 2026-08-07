# LinkedInBot
## AI Destekli İş İlanı Keşif ve Kariyer Asistanı — Product Requirements Document (PRD)

### Document Control

| Alan | Değer |
|---|---|
| Doküman Türü | Product Requirements Document (Living Document) |
| Proje Kod Adı | LinkedInBot |
| Versiyon | 1.3 |
| Durum | Draft — Aktif Geliştirme İçin Ana Referans Doküman |
| Product Owner / Tek Kullanıcı | Refik Sarıbıyık |
| Son Güncelleme | 2026-08-07 |
| Kapsam | V1 (MVP) tanımı + Uzun Vadeli Roadmap |

---

## Executive Summary

LinkedInBot, kullanıcının LinkedIn üzerinde iş ilanı arama sürecini otomatikleştiren, kişisel ve AI destekli bir iş keşif ve değerlendirme sistemidir. Sistem kullanıcı adına ilanları tarar, lokasyon/departman/deneyim seviyesi kriterlerine göre filtreler, şirketleri kalite açısından puanlar, her ilanı kullanıcı profiliyle AI aracılığıyla eşleştirir ve sonucu okunabilir, gerekçelendirilmiş bir raporla kullanıcıya sunar.

**İlk versiyonun (V1) amacı otomatik başvuru yapmak değildir.** Amaç, kullanıcının saatlerce manuel arama yapmak zorunda kalmadan sadece gerçekten uygun ilanlara odaklanabilmesini sağlamaktır. V1 kapsamı keşif, filtreleme, skorlama ve raporlama ile sınırlıdır; başvuru eylemi tamamen kullanıcının elinde kalır.

Uzun vadede LinkedInBot; CV optimizasyonu, otomatik başvuru, mülakat hazırlığı, başvuru takibi ve kariyer danışmanlığı gibi yeteneklerle genişleyerek kapsamlı bir kişisel **AI Career Assistant**'a evrilecektir (bkz. Section 18 — Future Roadmap).

**Kapsam Notu:** Bu doküman sistemin **ne** yapması ve **neden** yapması gerektiğini (What / Why) tanımlar. Uygulama platformu, teknik mimari detayları, workflow/node yapısı ve kod implementasyonu **bilinçli olarak** bu dokümanın kapsamı dışında tutulmuştur; bu konular ileride ayrı bir Technical Design / Implementation dokümanında ele alınacaktır. Bu PRD, o teknik çalışmanın referans alacağı sabit kaynaktır.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem Statement](#2-problem-statement)
3. [Vision](#3-vision)
4. [Goals](#4-goals)
5. [Success Metrics](#5-success-metrics)
6. [User Story](#6-user-story)
7. [Functional Requirements](#7-functional-requirements)
8. [Non-Functional Requirements](#8-non-functional-requirements)
9. [User Flow](#9-user-flow)
10. [Workflow](#10-workflow)
11. [Filtering Logic](#11-filtering-logic)
12. [Company Scoring Logic](#12-company-scoring-logic)
13. [AI Matching Logic](#13-ai-matching-logic)
14. [Scheduling](#14-scheduling)
15. [Data Model](#15-data-model)
16. [Reporting Format](#16-reporting-format)
17. [Configuration](#17-configuration)
18. [Future Roadmap](#18-future-roadmap)
19. [Risks](#19-risks)
20. [Edge Cases](#20-edge-cases)
21. [Technical Considerations](#21-technical-considerations)
22. [Assumptions](#22-assumptions)
- [Appendix A: Glossary](#appendix-a-glossary)
- [Appendix B: Version History](#appendix-b-version-history)

---

## 1. Project Overview

**Ürün Adı:** LinkedInBot (çalışma adı) — uzun vadede daha geniş bir **AI Career Assistant** ürün ailesinin ilk ve temel modülü.

**Ürün Tipi:** Kişisel kullanım için tasarlanmış, otomatik çalışan bir iş ilanı keşif, filtreleme, değerlendirme ve raporlama sistemi.

**Birincil Kullanıcı:** Tek kullanıcı — İstanbul'da, kurumsal/entry-level pozisyonlar arayan bir iş arayan profesyonel/yeni mezun. **V1'in ürün kapsamı tek kullanıcı içindir**; sistemin iç mimarisi ise gelecekte çok-kullanıcılı bir SaaS ürününe evrilmeyi büyük bir yeniden yazım gerektirmeden destekleyecek şekilde tasarlanır (bkz. aşağıda "Mimari Not").

**Problem, bir cümlede:** LinkedIn'de doğru ilanı bulmak, o ilanı değerlendirmekten çok daha fazla zaman alıyor; bu sistem o kaybı sıfıra indirmeyi hedefler.

**V1 Kapsamı — Dahil Olanlar:**
- LinkedIn'den otomatik ilan keşfi
- Lokasyon, departman ve deneyim seviyesi filtrelemesi (semantik anlama dahil)
- Şirket kalite puanlaması (Company Quality Score)
- AI destekli uygunluk puanlaması (AI Match Score) ve gerekçelendirme
- Departman bazlı, gerekçeli, Markdown formatında rapor + Top Matches bölümü
- Yeni / güncellenmiş / kapanmış ilan takibi (duplicate & closed detection)
- Otomatik (varsayılan iki günlük) çalışma + manuel tetikleme
- Kod değişikliği gerektirmeyen filtre konfigürasyonu

**V1 Kapsamı — Dahil Olmayanlar (Explicit Non-Goals):**
- Otomatik başvuru (Easy Apply automation)
- CV veya Cover Letter üretimi / optimizasyonu
- Başvuru takibi (Application Tracker)
- Mülakat hazırlığı, kariyer danışmanlığı, maaş tahmini
- Notion / Google Sheets / Airtable / Email / Telegram / Discord gibi harici çıktı entegrasyonları (V1 çıktısı sadece Markdown'dır)
- Çoklu kullanıcı desteği

**Mimari Not — Multi-Tenant Hazırlığı (Commercialization Readiness):**

V1'in *ürün kapsamı* tek kullanıcı ile sınırlı olsa da (yukarıdaki "Dahil Olmayanlar" — Çoklu kullanıcı desteği), bu sınır bir **ürün kararıdır, bir mimari kısıtlama değildir**. Sistem, ileride ticarileştirilerek çok-kullanıcılı bir SaaS ürününe dönüştürülebileceği varsayımıyla tasarlanır. Bu, aşağıdaki bağlayıcı mimari ilkelerle karşılanır (bkz. NFR-15, Section 15.0, Section 17.1, Section 21):

- Kullanıcıya özgü hiçbir tercih, eşik, ağırlık, prompt veya format kod içine gömülmez; tamamı konfigürasyon üzerinden yönetilir.
- Veri modeli, ilk günden itibaren bir **User/Account kimliği** etrafında kavramsal olarak bölümlenir (V1'de tek bir hesap var olsa dahi).
- İş mantığı (filtreleme, skorlama, raporlama) kullanıcı kimliğinden bağımsız, girdisi (ilan + şirket + kullanıcı konfigürasyonu) olan saf bir motor olarak tasarlanır.
- Bu ilkeler V1'in teslimat hızını veya basitliğini bozmaz; V1 tek bir kullanıcı/hesap kaydıyla çalışır, ancak ikinci bir hesabın eklenmesi mimari bir değişiklik değil, bir veri kaydı eklemesi olmalıdır.

**Stratejik Konum:** LinkedInBot, daha büyük bir "AI Career Assistant" vizyonunun **temel/keşif katmanıdır**. V1'in doğruluğu ve güvenilirliği, üzerine inşa edilecek tüm gelecek özelliklerin (Section 18) sağlam bir veri ve karar katmanına sahip olmasını garanti eder. Bu nedenle V1'in önceliği; hız veya özellik genişliği değil, **isabet ve şeffaflıktır.**

---

## 2. Problem Statement

**Mevcut Durum:** İş arama sürecinde kullanıcı, LinkedIn üzerinde düzenli olarak manuel aramalar yapmak zorunda kalıyor. Bu aramalar; farklı anahtar kelime kombinasyonları, tekrarlanan filtre denemeleri ve daha önce görülmüş ilanların yeniden gözden geçirilmesi nedeniyle önemli miktarda zaman tüketiyor.

**Ana Sorunlar:**

1. **Zaman Kaybı** — LinkedIn'in yerleşik arama/filtre deneyimi, kullanıcının aradığı nüanslı kriterleri (departman benzerliği, kariyer seviyesi, şirket prestiji) desteklemiyor; kullanıcı bu filtrelemeyi manuel olarak zihninde yapmak zorunda kalıyor.
2. **Tutarsız Değerlendirme** — Manuel değerlendirme sırasında yorgunluk, dikkat dağınıklığı veya zaman baskısı nedeniyle bazı ilanlar hak ettiğinden az veya çok değer görebiliyor; değerlendirme kriterleri gün içinde tutarlılığını kaybedebiliyor.
3. **Şirket Kalitesi Görünmezliği** — Arama sonuçları şirketin prestijini, büyüklüğünü veya kariyer gelişimi potansiyelini öne çıkarmıyor; kullanıcı her ilan için şirketi ayrıca manuel araştırmak zorunda kalıyor.
4. **Tekrar ve Gürültü** — Aynı ilanla farklı zamanlarda tekrar karşılaşılıyor, kapanmış ilanlar hâlâ görünür durumda kalabiliyor; bu da gerçek fırsatların gürültü içinde kaybolmasına yol açıyor.
5. **Gerekçe Eksikliği** — Kullanıcı bir ilana neden "uygun" veya "uygun değil" dediğini sistematik olarak kaydetmiyor; bu da zamanla tutarlı bir değerlendirme mantığı oluşmasını engelliyor.
6. **Ölçeklenemeyen Dikkat** — Günde onlarca ilanı aynı titizlikle değerlendirmek, insan dikkatinin doğal sınırlarını zorluyor.

**Sonuç:** Kullanıcı, asıl değerli olan aktiviteye — *doğru ilana kaliteli bir başvuru hazırlamaya* — ayırması gereken zaman ve enerjiyi, *doğru ilanı bulmaya* harcıyor. LinkedInBot bu dengesizliği tersine çevirmeyi hedefler.

---

## 3. Vision

**Uzun Vadeli Vizyon:** LinkedInBot, zamanla kullanıcının kariyerini uçtan uca yöneten kişisel bir **AI Career Assistant**'a dönüşecektir — iş keşfinden başvuru hazırlığına, mülakat sürecine ve kariyer gelişimi tavsiyelerine kadar tüm süreci destekleyen bir sistem.

**V1'in Vizyondaki Rolü:** V1, bu büyük vizyonun **temel katmanıdır**: güvenilir, açıklanabilir ve doğru filtrelenmiş bir iş ilanı keşif motoru. Üzerine inşa edilecek her şey (CV optimizasyonu, otomatik başvuru, mülakat hazırlığı) bu temel katmanın doğruluğuna bağımlıdır — yanlış ilanlar üzerine kurulan bir otomasyon, sonraki tüm katmanlarda değersizleşir.

**Tasarım Felsefesi:**

- **Human-in-the-loop:** Sistem karar vermez, öneri sunar. Nihai kontrol her zaman kullanıcıda kalır — özellikle V1'de başvuru eylemi tamamen kullanıcıya aittir.
- **Explainability (Açıklanabilirlik):** Her skor ve her filtreleme kararı bir gerekçeyle desteklenir. Hedef, "kara kutu" bir sistem değil, şeffaf bir karar destek sistemidir.
- **Configurability (Yapılandırılabilirlik):** Kullanıcının kariyer hedefleri zamanla değişebilir (departman, lokasyon, seviye). Sistem bu değişime kod yazmadan uyum sağlayabilmelidir.
- **Kademeli Otonomi (Progressive Autonomy):** Sistem, kanıtlanmış güvenilirlik üzerine zamanla daha fazla otonomi kazanır — önce sadece bulma, sonra öneri ve gerekçelendirme, ardından (kullanıcı onayıyla) eylem.
- **Ticarileştirmeye Hazır Mimari (Multi-Tenant-Ready Architecture):** Sistem bugün tek kullanıcı için çalışsa da, mimari hiçbir noktada "tek kullanıcı" varsayımını iş mantığına gömmez. Kullanıcıya özgü her şey (tercihler, eşikler, ağırlıklar, prompt'lar, bildirim ayarları, rapor formatı) veri/konfigürasyon katmanında yaşar; böylece ürün gelecekte çok-kullanıcılı bir SaaS'a dönüştüğünde çekirdek filtreleme/skorlama/raporlama motorunun yeniden yazılması gerekmez (bkz. NFR-15).

**North Star:** Kullanıcının LinkedIn'de "ilan aramak" için hiç zaman harcamadığı; sadece sistemin sunduğu, gerekçelendirilmiş ve kaliteli fırsatlar arasından seçim yaptığı, kariyer sürecinin her adımında (başvuru, mülakat, gelişim) AI desteği aldığı bir gelecek.

---

## 4. Goals

**V1 Ürün Hedefleri (Kısa Vade)**

| ID | Hedef | Açıklama |
|---|---|---|
| G-1 | Manuel arama süresini ortadan kaldırmak | Kullanıcının LinkedIn'de aktif arama yapma ihtiyacını pratikte sıfıra indirmek |
| G-2 | Yüksek isabetli filtreleme | Rapora giren ilanların büyük çoğunluğunun kullanıcı tarafından "gerçekten uygun" bulunması |
| G-3 | Şeffaf değerlendirme | Her ilan ve şirket kararının anlaşılır bir gerekçeyle sunulması |
| G-4 | Sıfır tekrar / sıfır gürültü | Aynı ilanın tekrar raporlanmaması, kapanmış ilanların elenmesi |
| G-5 | Kod değiştirmeden yapılandırılabilirlik | Lokasyon, departman, deneyim seviyesi ve eşik değerlerinin konfigürasyon üzerinden değiştirilebilmesi |
| G-6 | Güvenilir otomasyon döngüsü | Planlanan çalıştırmaların istikrarlı ve öngörülebilir şekilde tamamlanması |

**Uzun Vadeli Stratejik Hedefler**

| ID | Hedef | Açıklama |
|---|---|---|
| G-7 | Uçtan uca kariyer asistanına genişleme | Keşiften başvuru takibine, mülakat hazırlığına kadar tüm süreci kapsayan bir sisteme evrilmek |
| G-8 | Genişletilebilir mimari | Her yeni roadmap özelliğinin çekirdek sistemi bozmadan eklenebilmesi |
| G-9 | Veriye dayalı kariyer zekası | Zamanla biriken ilan ve şirket verisiyle kişisel pazar/trend içgörüleri üretebilme |
| G-10 | Ticarileştirmeye hazır mimari | Mimarinin, çok-kullanıcılı bir SaaS ürününe büyük bir yeniden yazım gerektirmeden evrilebilmesi (bkz. NFR-15) |

---

## 5. Success Metrics

Bu metrikler kişisel, tek-kullanıcılı bir proje bağlamında tanımlanmıştır. V1'de bazı metrikler manuel/öznel olarak (kullanıcının kendi değerlendirmesiyle) takip edilecek; ileride **Personal Dashboard** (Section 18) ile otomatikleştirilecektir.

**Verimlilik Metrikleri**
- Haftalık manuel LinkedIn arama süresi — hedef: mevcut duruma göre **%90+ azalma**
- Rapor başına inceleme süresi — hedef: **<10 dakika**

**Kalite / İsabet Metrikleri**
- **Precision:** Rapordaki ilanların kullanıcı tarafından "gerçekten uygun" bulunma oranı — hedef: **≥%80**
- **False Positive Rate:** Rapora giren ama açıkça uygunsuz ilan oranı — hedef: **<%10**
- **False Negative Spot-Check:** Periyodik manuel kontrolde, filtre dışı kalan ilanlar arasında gözden kaçmış uygun ilan oranı — hedef: mümkün olan en düşük seviye (bkz. Section 20 — Borderline bucket önerisi)

**Kapsama Metrikleri**
- Döngü başına keşfedilen benzersiz ilan sayısı
- Döngü başına keşfedilen benzersiz şirket sayısı

**Güvenilirlik Metrikleri**
- **Run Success Rate:** Planlanan çalıştırmaların başarıyla tamamlanma oranı — hedef: **≥%95**
- **Duplicate Rate:** Aynı ilanın birden fazla raporda "yeni" (NEW) olarak görünme oranı — hedef: **%0**. *Netleştirme: Bu metrik yalnızca NEW etiketiyle tekrar görünmeyi kapsar; hâlâ açık ve güçlü bir ilanın Top Matches bölümünde etiketsiz olarak tekrar görünmesi (bkz. Section 16.3, Section 16.4) bu metriğin ihlali sayılmaz — bu davranış kasıtlı bir tasarım kararıdır.*
- **Stale Listing Rate:** Kapanmış ama hâlâ raporda görünen ilan oranı — hedef: **%0**

**Sonuç Metrikleri (Proxy)**
> V1'de otomatik başvuru olmadığından, gerçek "başarı" dolaylı ölçülür.
- Top Matches bölümünden gerçekleşen başvuru oranı
- Company Quality Score eşiğinin üzerindeki şirketlere yapılan başvuru oranı ("kalite-ayarlı başvuru oranı")

**North Star Metric:** *Kalite-ayarlı zaman-başına-uygun-fırsat oranı* — kullanıcının birim zaman başına önüne gelen, hem AI Match Score hem Company Quality Score eşiklerini geçen fırsat sayısı.

---

## 6. User Story

**Birincil Persona**

> Yeni mezun / kariyerinin erken döneminde, İstanbul'da yaşayan, kurumsal ortamda Business Development, Strategy, Marketing, Trade veya Consulting alanlarında entry-level bir pozisyon arayan bir profesyonel. LinkedIn'i aktif takip ediyor ancak manuel arama sürecinden bıkmış durumda; itibarlı, kariyer gelişimi sağlayan şirketlerde çalışmayı önemsiyor.

**Kullanıcı Hikâyeleri**

- **US-1:** Bir iş arayan olarak, LinkedIn'de manuel arama yapmak istemiyorum, çünkü zamanımı sadece gerçekten uygun ilanlara başvurarak geçirmek istiyorum.
- **US-2:** Bir iş arayan olarak, sadece İstanbul'da veya İstanbul merkezli uzaktan/hibrit pozisyonları görmek istiyorum, çünkü lokasyon benim için değişmez bir kriter.
- **US-3:** Bir iş arayan olarak, ilgi alanıma yakın tüm departman varyasyonlarının (listede birebir olmayan ama anlamca yakın unvanlar dahil) yakalanmasını istiyorum, çünkü unvan isimlendirmeleri şirketten şirkete değişiyor.
- **US-4:** Bir iş arayan olarak, sadece deneyim seviyeme uygun ilanları görmek istiyorum, çünkü kıdemli pozisyonlara zaman harcamak istemiyorum.
- **US-5:** Bir iş arayan olarak, her ilanın yanında şirketin kalite/prestij puanını görmek istiyorum, çünkü kariyerim için doğru şirketi seçmek benim için kritik.
- **US-6:** Bir iş arayan olarak, her ilan için neden bana önerildiğini açıkça görmek istiyorum, çünkü sisteme güvenmek için gerekçeyi anlamam gerekiyor.
- **US-7:** Bir iş arayan olarak, daha önce gördüğüm ilanları tekrar görmek istemiyorum, çünkü bu zamanımı çalar ve raporu gürültülü hale getirir.
- **US-8:** Bir iş arayan olarak, kapanmış ilanların raporda görünmemesini istiyorum, çünkü kapanmış bir ilana zaman ayırmak istemiyorum.
- **US-9:** Bir iş arayan olarak, en iyi 10 ilanı ayrıca görmek istiyorum, çünkü sınırlı zamanımda önce en yüksek potansiyelli fırsatlara bakmak istiyorum.
- **US-10:** Bir iş arayan olarak, filtre kriterlerimi (lokasyon, departman, seviye) kolayca değiştirebilmek istiyorum, çünkü kariyer hedeflerim zamanla değişebilir.
- **US-11:** Bir iş arayan olarak, sistemi istediğim an manuel olarak da çalıştırabilmek istiyorum, çünkü otomatik döngüyü beklemeden güncel durumu görmek isteyebilirim.

---

## 7. Functional Requirements

Öncelik seviyeleri MoSCoW yöntemine göre belirlenmiştir: **Must-have** (V1 için zorunlu), **Should-have** (değerli, ilk sürümde kısmi/basit implementasyonla kabul edilebilir).

### Must-have

**FR-1 — LinkedIn Session Authentication**
- **Açıklama:** Sistem, kullanıcının kişisel LinkedIn hesabı üzerinden oturum açarak ilan verisine erişir.
- **Kabul Kriterleri:** Oturum geçersiz/süresi dolmuşsa sistem bunu sessizce yutmaz, açıkça tespit eder ve işaretler; kimlik bilgileri güvenli şekilde saklanır (bkz. Section 21). V1'de aktif bir bildirim kanalı (Section 18 Phase 2'ye kadar) bulunmadığından, oturum hatası en azından yerel olarak görünür bir durum sinyaliyle (bkz. FR-15 Run Log) işaretlenir; sistem hiçbir koşulda hatayı sessizce yutup bir sonraki çizelgeye geçmez.

**FR-2 — Job Posting Discovery / Collection**
- **Açıklama:** Sistem, her çalıştırmada temel arama kapsamına (lokasyon + geniş rol anahtar kelimeleri) uyan ilanları toplar.
- **Kabul Kriterleri:** Toplanan her ilan, sonraki filtreleme adımları için gerekli minimum alanlara (başlık, şirket, lokasyon, tarih, açıklama, link) sahiptir; tekil bir kaydın hatalı/eksik olması tüm çalıştırmayı durdurmaz.

**FR-3 — Location Filtering**
- **Açıklama:** Section 11'de tanımlanan lokasyon mantığına göre ilanlar filtrelenir.
- **Kabul Kriterleri:** İstanbul dışı ve merkezi İstanbul olmayan uzaktan/hibrit ilanlar elenir; belirsiz lokasyon bilgisi Section 20'de tanımlanan şekilde ele alınır.

**FR-4 — Department & Role Relevance Filtering (Semantic)**
- **Açıklama:** İlan başlığı/açıklaması, Section 11'de tanımlanan departman taksonomisiyle **semantik olarak** karşılaştırılır; sadece birebir kelime eşleşmesiyle sınırlı kalınmaz.
- **Kabul Kriterleri:** Listede birebir yer almayan ama anlamca yakın unvanlar (örneğin yerel/yaratıcı unvan varyasyonları) da yakalanabilir; eşleşme bir güven skoruna dayanır ve eşik konfigüre edilebilir (varsayılan eşik: **0.65** — bkz. Section 11.2, Section 17).

**FR-5 — Experience Level Filtering**
- **Açıklama:** İlan, Section 11'de tanımlanan deneyim seviyesi listesine göre değerlendirilir; açıkça kıdemli sinyaller (unvan veya yıl gereksinimi) taşıyan ilanlar elenir.
- **Kabul Kriterleri:** Deneyim seviyesi ilanda açıkça etiketlenmemişse sistem içerik üzerinden çıkarım yapar; belirsiz durumlar Section 20'de tanımlanır. Başlık ve açıklama arasında çelişkili kıdem sinyali varsa (örn. başlık "Junior Analyst", açıklama "5+ years experience"), **açıklama metnindeki sinyal önceliklidir** çünkü başlık pazarlama amaçlı basitleştirilmiş olabilir (bkz. EDGE-12).

**FR-6 — Company Quality Scoring**
- **Açıklama:** Filtrelerden geçen her ilanın şirketi, Section 12'deki rubrik doğrultusunda 0-100 arası bir **Company Quality Score** ile puanlanır.
- **Kabul Kriterleri:** Her skor, alt boyut kırılımıyla (brand, ölçek, kariyer gelişimi vb.) izlenebilir olur; skor hesaplanamayan şirketler "Unrated" olarak işaretlenir, sessizce dışlanmaz. Bir şirket daha önce değerlendirilmişse ve `Last Evaluated Timestamp` (bkz. Section 15.3) konfigüre edilebilir bir tazelik penceresinin (varsayılan: 30 gün — bkz. Section 12.4, Section 17) içindeyse, şirket yeniden puanlanmaz; mevcut skor doğrudan yeniden kullanılır.

**FR-7 — AI Match Scoring & Rationale Generation**
- **Açıklama:** Her ilan, kullanıcı profiliyle karşılaştırılarak Section 13'teki mantığa göre 0-100 arası bir **AI Match Score** alır ve skora eşlik eden bir gerekçe listesi ("Selected because…") üretilir.
- **Kabul Kriterleri:** Gerekçe listesi en az 3 madde içerir ve skorun bileşenlerini (lokasyon, seviye, departman, şirket kalitesi, kariyer hedefi uyumu) yansıtır. Gerekçe maddeleri **yalnızca sistemin hesapladığı yapısal skor bileşenlerine dayanır** (serbest, doğrulanamayan LLM yorumu üretilmez); örneğin bir şirket "Unrated" ise gerekçe listesi o şirketi asla "prestigious" gibi doğrulanmamış bir nitelemeyle sunamaz (bkz. Section 13.2, RISK-10).

**FR-8 — Duplicate Detection (Cross-Run)**
- **Açıklama:** Bir ilan daha önce raporlandıysa ve içeriği değişmediyse, sonraki raporlarda tekrar gösterilmez.
- **Kabul Kriterleri:** Sistem her ilan için kalıcı bir kimlik takip eder; aynı kimlik iki farklı çalıştırmada "yeni" olarak işaretlenmez.

**FR-9 — New Job Detection & Tagging**
- **Açıklama:** İlk kez görülen ilanlar raporda **NEW** etiketiyle gösterilir.
- **Kabul Kriterleri:** Etiket yalnızca gerçekten daha önce hiç görülmemiş ilanlara uygulanır.

**FR-10 — Closed Job Detection & Suppression**
- **Açıklama:** Başvuruya kapanmış ilanlar sonraki raporlarda gösterilmez.
- **Kabul Kriterleri:** Kapalı durumu tespit edilen bir ilan, veri modelinde "Closed" olarak işaretlenir ve aktif rapor akışından çıkarılır (geçmiş kayıt silinmez, bkz. Section 15).

**FR-11 — Report Generation (Grouped + Top Matches)**
- **Açıklama:** Section 16'da tanımlanan formatta, departman bazlı gruplanmış ve Top Matches bölümü içeren bir Markdown raporu üretilir.
- **Kabul Kriterleri:** Her ilan girdisi gerekli tüm alanları (Firma, Pozisyon, Lokasyon, Yayın Tarihi, AI Match Score, Company Quality Score, Easy Apply, Başvuru Linki) ve gerekçe bloğunu içerir; Top Matches bölümü AI Match Score'a göre sıralı ilk 10 ilanı listeler.

**FR-12 — Scheduling (Automatic + Manual Trigger)**
- **Açıklama:** Sistem varsayılan olarak iki günde bir otomatik çalışır; kullanıcı istediği zaman manuel olarak da tetikleyebilir.
- **Kabul Kriterleri:** Manuel tetikleme otomatik çizelgeyi bozmaz; aynı anda birden fazla çalıştırma başlatılmaz (bkz. Section 14).

**FR-13 — Configuration Management**
- **Açıklama:** Lokasyon, departman listesi, deneyim seviyesi listesi, Company Quality Score eşiği ve AI Match Score eşiği kod değişikliği gerektirmeden güncellenebilir.
- **Kabul Kriterleri:** Bir kriterin değiştirilmesi (örn. İstanbul → Ankara) sistemin başka hiçbir bölümünde değişiklik gerektirmez. Geçersiz veya şema dışı bir konfigürasyon (örn. yanlış yazılmış bir departman adı, toplamı %100 etmeyen ağırlıklar) çalıştırma başlamadan **açıkça reddedilir ve hata olarak raporlanır**; sistem hiçbir zaman geçersiz konfigürasyonu sessizce göz ardı ederek varsayılan davranışa geri dönmez (bkz. EDGE-15).

### Should-have

**FR-14 — Updated Job Detection & Tagging**
- **Açıklama:** Daha önce raporlanmış bir ilanın içeriğinde anlamlı bir değişiklik (unvan, seviye, lokasyon, açıklama) olduğunda ilan **UPDATED** etiketiyle yeniden gösterilir.
- **Kabul Kriterleri:** Kozmetik/önemsiz değişiklikler (yazım hatası düzeltmesi gibi) etiketi tetiklemez (bkz. Section 20). "Anlamlı değişiklik" en az şu alanlardan birinin değerinde bir değişikliği kapsar: Title, Experience Level (çıkarımı), Location, Workplace Type veya Description'ın filtreleme/skorlama sonucunu etkileyecek ölçüde değişmesi; salt biçimlendirme, yazım veya kelime sırası farkları hariçtir. Kesin benzerlik eşiği/algoritması teknik tasarım aşamasında belirlenir, ancak bu alan listesi UPDATED tetikleyicisinin kapsamını sınırlayan bağlayıcı bir gereksinimdir.

**FR-15 — Run Logging / Execution History**
- **Açıklama:** Her çalıştırma için temel bir çalıştırma kaydı (zaman, tetikleme tipi, toplanan/filtrelenen/yeni/kapanan ilan sayıları, hata durumu) tutulur.
- **Kabul Kriterleri:** Bir çalıştırma başarısız olursa bu durum sonraki incelemede görünür olur; sessiz hata oluşmaz.

**FR-16 — Borderline Match Review Bucket**
- **Açıklama:** AI Match Score, dışlama eşiğine çok yakın (örn. eşik 60 ise 55-60 arası) ilanlar tamamen elenmek yerine ayrı, düşük öncelikli bir bölümde işaretlenir.
- **Kabul Kriterleri:** Borderline ilanlar ana departman gruplarından ayrı, açıkça etiketlenmiş şekilde sunulur (bkz. Section 20). Borderline bant genişliği varsayılan olarak eşik değerinin **5 puan altı** olarak tanımlanır (örn. eşik 60 ise 55-60 arası) ve konfigüre edilebilir bir parametredir (bkz. Section 17); bant yalnızca eşiğin altına doğru tanımlıdır.

**FR-17 — Report Artifact Persistence**
- **Açıklama:** Her çalıştırma, önceki raporların üzerine yazılmadan, kendi Report ID'siyle (bkz. Section 15.5) ayrı ve kalıcı bir Markdown dosyası olarak saklanır.
- **Kabul Kriterleri:** Bir önceki çalıştırmanın raporu, yeni bir rapor üretildikten sonra da erişilebilir kalır; "Previously Reported" etiketlemesi (bkz. Section 16.1, Section 16.3) bu geçmiş rapor kaydına dayanarak doğrulanabilir.

**FR-18 — Score & Evaluation Caching**
- **Açıklama:** İçeriği değişmemiş bir ilan veya konfigüre edilebilir bir tazelik penceresi içinde daha önce değerlendirilmiş bir şirket, tekrar AI/LLM çağrısına tabi tutulmadan önceki skoruyla yeniden kullanılır (bkz. FR-6).
- **Kabul Kriterleri:** Aynı içerikli bir ilanın art arda çalıştırmalarda tekrar puanlanmadığı doğrulanabilir; bu davranış NFR-9 (Cost Efficiency) ve NFR-1 (Performance) hedeflerini doğrudan destekler. AI Match Score, tanım gereği kullanıcıya özgü girdilere (kariyer hedefi, ağırlıklar) dayandığından, önbellek anahtarı her zaman **Job ID + User/Account ID + Config Version** üçlüsüyle kapsamlanır (bkz. Section 15.0, NFR-15); ham ilan/şirket verisinin toplanması (Collection) ise hesaplar arasında paylaşılabilir bir katmandır. İçerik değişikliği tespiti (ve dolayısıyla önbellek geçerliliği), FR-14'teki "anlamlı değişiklik" alan kapsamıyla (Title, Experience Level, Location, Workplace Type, Description) aynı temele dayanır; kozmetik veya oynak alanlar (örn. görüntülenme sayısı, göreli zaman ifadeleri) bu belirlemeyi etkilemez.

**FR-19 — Job & Company Exclusion (Blacklist)**
- **Açıklama:** Kullanıcı, belirli bir şirketi veya belirli bir ilanı kod değişikliği gerektirmeden, konfigürasyon üzerinden kalıcı olarak dışlayabilir.
- **Kabul Kriterleri:** Dışlanan bir şirket/ilan, tüm filtrelerden geçse ve yüksek skor alsa dahi hiçbir raporda (Top Matches dahil) görünmez; dışlama listesi Section 15.1'deki "Preferences / Dealbreakers" alanı üzerinden yönetilir.

**FR-20 — Bootstrap / Cold-Start Run Handling**
- **Açıklama:** Job History Store boşken (sistemin ilk çalıştırması) üretilen ilk rapor, tüm sonuçları normal "NEW" akışıyla değil, açıkça işaretlenmiş bir "İlk Tarama / Başlangıç Envanteri" (Bootstrap) bölümü olarak sunar.
- **Kabul Kriterleri:** Kullanıcı, ilk raporun tek seferlik büyük hacimli bir başlangıç taraması olduğunu, sürekli tekrar edecek bir "NEW" hacmi olmadığını raporun kendisinden anlayabilir (bkz. EDGE-13).

**FR-21 — Collection Volume Bound**
- **Açıklama:** Her çalıştırmada toplanacak maksimum ilan/sayfa sayısı konfigüre edilebilir bir üst sınıra sahiptir.
- **Kabul Kriterleri:** Bir çalıştırma bu sınıra ulaştığında toplamayı durdurur ve bu durumu (sınıra ulaşıldığı için toplamanın kesildiğini) Run Log'da açıkça belirtir (bkz. FR-15); çalıştırma süresi ve maliyeti bu sayede öngörülebilir kalır.

---

## 8. Non-Functional Requirements

| ID | Kategori | Gereksinim | Hedef / Gerekçe |
|---|---|---|---|
| NFR-1 | Performance | Bir çalıştırma döngüsü, kullanıcıyı bloklamadan makul bir sürede tamamlanmalı | Günlük iş akışını kesmemeli |
| NFR-2 | Reliability | Planlanan çalıştırmaların büyük çoğunluğu başarıyla tamamlanmalı | ≥%95 run success rate (bkz. Section 5) |
| NFR-3 | Security & Privacy | LinkedIn kimlik bilgileri/oturum verisi ve kişisel profil verisi güvenli şekilde saklanmalı | Kişisel hesap güvenliği |
| NFR-4 | Compliance Risk Awareness | Sistem, LinkedIn kullanım şartları kapsamındaki otomasyon riskinin farkında tasarlanmalı | Hesap sağlığının korunması (bkz. Section 19) |
| NFR-5 | Maintainability | Filtreleme, skorlama ve raporlama mantığı birbirinden ayrıştırılmış modüller olarak tasarlanmalı | Roadmap özelliklerinin kolayca eklenebilmesi |
| NFR-6 | Configurability | Filtreler, skorlama ağırlıkları, prompt şablonları, çizelgeleme, bildirim ayarları ve rapor formatı dahil tüm kullanıcıya özgü tercihler kod değişikliği gerektirmeden değiştirilebilmeli | Kullanıcı bağımsızlığı ve gelecekteki çok-kullanıcı desteği (bkz. Section 17, Section 17.1, NFR-15) |
| NFR-7 | Usability | Rapor, teknik olmayan bir okuyucu için bile kolay okunabilir olmalı | Ana çıktının kullanılabilirliği |
| NFR-8 | Extensibility | Mimari, gelecekteki entegrasyonları ve yeni filtre/skorlama kriterlerini, mümkün olduğunca kod değişikliği gerektirmeden, mevcut çekirdek mantığı bozmadan destekleyebilmeli | Roadmap'in ve yeni kriterlerin teknik borç yaratmadan uygulanabilmesi |
| NFR-9 | Cost Efficiency | AI/LLM kullanım maliyeti, ilan hacmiyle orantılı ve öngörülebilir olmalı; değişmemiş ilan/şirket verisi tekrar puanlanmamalı (bkz. FR-18) | Kişisel proje bütçesi |
| NFR-10 | Observability | Her çalıştırma için temel bir çalıştırma kaydı tutulmalı | Sessiz hataların fark edilmesi |
| NFR-11 | Data Retention | Geçmiş ilan ve şirket verisi silinmeden saklanmalı | Career Trend Analysis gibi gelecekteki özellikler için geçmiş veri gereksinimi |
| NFR-12 | Consistency | Aynı ilan/şirket, farklı çalıştırmalarda tutarlı skorlara sahip olmalı | Kullanıcı güveni; skor "gürültüsü" güveni azaltır |
| NFR-13 | Run Atomicity | Bir çalıştırma tamamlanmadan kesintiye uğrarsa (örn. çökme), Job History Store tutarsız/yarı-güncellenmiş bir durumda kalmamalı | Idempotency ve veri bütünlüğü (bkz. Section 21, EDGE-14) |
| NFR-14 | Detectability Risk Reduction | Sabit çizelge (Section 14) etrafında küçük, konfigüre edilebilir bir zamanlama sapması (jitter) uygulanmalı | Tamamen periyodik bot davranışının otomasyon tespiti riskini azaltmak (bkz. RISK-1) |
| NFR-15 | Multi-Tenancy Readiness | Kullanıcıya özgü hiçbir veri, tercih veya kural iş mantığına gömülmemeli; tüm kullanıcı/hesap verisi ve konfigürasyonu, ileride çok-kullanıcılı bir yapıya geçişi büyük bir yeniden yazım gerektirmeden mümkün kılacak şekilde izole tutulmalı | Ticarileştirme / SaaS dönüşüm hazırlığı (bkz. Section 1 "Mimari Not", Section 15.0, Section 17.1, Section 21) |

---

## 9. User Flow

Bu bölüm sistemin **kullanıcı gözünden** deneyimini tanımlar (kullanıcının ne gördüğü ve ne yaptığı). Sistemin iç işleyişi için bkz. Section 10 — Workflow.

1. Otomatik çizelge tetiklenir **veya** kullanıcı manuel olarak çalıştırmayı başlatır.
2. Kullanıcı bu süreçte aktif bir eylemde bulunmaz; sistem arka planda çalışır.
3. Çalıştırma tamamlandığında kullanıcıya güncel bir rapor sunulur (V1'de Markdown dosyası).
4. Kullanıcı raporu açar; önce **Top Matches** bölümüne, ardından ilgilendiği departman gruplarına göz atar.
5. Kullanıcı her ilanın yanındaki **AI Match Score**, **Company Quality Score** ve "Selected because" gerekçesini inceler.
6. Kullanıcı ilgisini çeken ilanlar için **Başvuru Linki** üzerinden LinkedIn'e giderek başvurusunu kendisi tamamlar (V1'de başvuru sistem dışındadır).
7. Bir sonraki döngüde kullanıcı yalnızca **NEW** veya **UPDATED** etiketli ilanları ve güncel **Top Matches** listesini görür; daha önce incelediği ve değişmeyen ilanlarla tekrar karşılaşmaz.
8. Kullanıcı kariyer hedefleri değiştiğinde (örneğin hedef şehir veya departman), konfigürasyonu günceller; bir sonraki çalıştırma yeni kriterlere göre sonuç üretir.

---

## 10. Workflow

Bu bölüm sistemin **iç mantığını**, uçtan uca işlenen veri akışını, araçtan/platformdan bağımsız şekilde tanımlar. Somut implementasyon (otomasyon platformu, node/adım yapısı, kod) bu dokümanın kapsamı dışındadır ve ayrı bir teknik tasarım aşamasında ele alınacaktır.

**Mantıksal İşlem Hattı (Logical Processing Pipeline):**

1. **Tetikleme (Trigger)** — Otomatik çizelge veya manuel kullanıcı isteği.
2. **Oturum Doğrulama (Session Validation)** — LinkedIn oturumunun geçerliliği kontrol edilir; geçersizse çalıştırma durur ve durum işaretlenir.
3. **İlan Toplama (Collection)** — Konfigüre edilmiş lokasyon ve geniş rol kapsamına göre, konfigüre edilebilir bir üst sınır dahilinde ham ilan verisi toplanır (bkz. FR-21).
4. **Normalizasyon (Normalization)** — Ham veri, iç veri modeline (Section 15) uygun, temizlenmiş ve standart alanlara dönüştürülür.
5. **Geçmişle Çapraz Kontrol (Historical Cross-Reference)** — Her ilan, geçmiş kayıtlarla karşılaştırılarak **New / Seen / Updated / Closed** durumlarından birine atanır.
6. **Filtreleme Motoru (Filtering Engine)** — Lokasyon → Deneyim Seviyesi → Departman/Rol İlgisi filtreleri sırayla uygulanır (Section 11).
7. **Şirket Kalite Puanlaması (Company Quality Scoring)** — Filtrelerden geçen ilanların şirketleri puanlanır (Section 12); tazelik penceresi içinde daha önce puanlanmış şirketler yeniden puanlanmaz (bkz. FR-6, FR-18, Section 12.4).
8. **AI Eşleştirme Motoru (AI Matching Engine)** — Her ilan kullanıcı profiliyle karşılaştırılır; AI Match Score ve yapısal skor bileşenlerine dayalı gerekçe üretilir (Section 13); içeriği değişmemiş ilanlar için önceki skor yeniden kullanılır (bkz. FR-18).
9. **Sıralama ve Gruplama (Ranking & Grouping)** — İlanlar departmana göre gruplanır; Top 10 hesaplanır.
10. **Rapor Derleme (Report Compilation)** — Section 16'daki formatta rapor oluşturulur.
11. **Durum Güncelleme (State Update)** — Raporlanan ilanlar "seen" olarak işaretlenir; kapanan ilanlar "closed" olarak güncellenir.
12. **Kayıt (Logging)** — Çalıştırma özeti (sayılar, hata durumu) kaydedilir ve hata/başarısızlık durumu en az yerel olarak görünür bir sinyalle işaretlenir (FR-15, FR-1).

---

## 11. Filtering Logic

Bir ilanın rapora girebilmesi için **Location AND Experience Level AND Department Relevance** koşullarının tümünü sağlaması gerekir (mantıksal VE). Departman filtresi, kesin ikili (evet/hayır) olmaktan çok bir **ilgi skoruna** dayanır ve konfigüre edilebilir bir eşik uygulanır.

### 11.1 Location Filtering

- Sadece **İstanbul** kabul edilir (varsayılan konfigürasyon).
- Uzaktan (Remote) veya hibrit ilanlar, şirketin/pozisyonun **İstanbul merkezli** olması durumunda tercih edilir.
- Lokasyon bilgisi belirsiz veya eksikse (örn. sadece "Remote - Turkey"), Section 20'de tanımlanan fallback mantığı uygulanır.

### 11.2 Department Filtering (Semantic)

Departmanlar altı ana kümede (cluster) toplanır. Listeler **örnek/başlangıç kümesidir**; AI, listede birebir olmayan ama anlamca yakın unvanları da (örn. yerelleştirilmiş veya yaratıcı unvan varyasyonları) tanıyabilmelidir — salt anahtar kelime eşleşmesi yeterli görülmez.

| Küme | Örnek Unvanlar |
|---|---|
| Sales & Business Development | Sales, Sales Executive, Key Account, Account Management, Business Development, Business Development Executive, Business Development Specialist |
| Strategy & Growth | Strategy, Strategic Planning, Corporate Strategy, Growth, Growth Strategy, Strategy & Business Development |
| Marketing | Marketing, Digital Marketing, Brand Marketing, Product Marketing |
| Trade, Logistics & Supply Chain | Trade, International Trade, Foreign Trade, Export, Import, Logistics, Supply Chain |
| Commercial | Commercial, Commercial Excellence |
| Consulting | Consulting, Management Consulting, Business Consulting |

**Semantik eşleştirme prensibi:** Eşleştirme motoru bir **güven skoru** üretir (0-1 ölçeğinde); yalnızca bu skor konfigüre edilebilir bir eşiğin üzerinde olan ilanlar ilerler. Varsayılan eşik **0.65**'tir (bkz. Section 17). Bu, listeye birebir uymayan ama alan uzmanlığıyla açıkça ilişkili unvanların (örn. "Ticaret Uzman Yardımcısı", "BD Associate") de yakalanmasını sağlar.

### 11.3 Experience Level Filtering

| Kabul Edilen Seviyeler |
|---|
| Internship |
| New Graduate |
| Entry Level |
| Graduate Program |
| Management Trainee |
| MT Program |
| 0-2 Years Experience |
| Junior |

**Dışlama prensibi:** İlan açıkça bu seviyelerden birine etiketlenmemiş olsa bile, içerik kıdem sinyalleri taşıyorsa (örn. "3+ years", "Manager", "Team Lead" — "Management Trainee" istisnası hariç) ilan elenir. Deneyim seviyesi belirsizse Section 20'deki fallback uygulanır. Başlık ile açıklama metni arasında çelişki varsa açıklama metnindeki sinyal esas alınır (bkz. FR-5, EDGE-12).

### 11.4 Filtre Yürütme Sırası

Öneri: **Location → Experience Level → Department Relevance**, çünkü lokasyon ve deneyim seviyesi ikili (binary) ve daha ucuz kontrol edilebilir sinyallerdir; departman ilgisi (semantik, AI-destekli) yalnızca ilk iki filtreyi geçen ilanlar için çalıştırılır. Bu sıralama gereksiz AI kullanımını (ve maliyetini) azaltır.

---

## 12. Company Scoring Logic

Her ilan, filtrelerden geçtikten sonra şirketinin **Company Quality Score**'unu (0-100) alır.

### 12.1 Skorlama Boyutları (Varsayılan, Konfigüre Edilebilir Ağırlıklar)

| Boyut | Açıklama | Varsayılan Ağırlık |
|---|---|---|
| Marka Bilinirliği & Prestij | Şirketin sektöründe ne kadar tanınır/saygın olduğu | %25 |
| Şirket Ölçeği | Çalışan sayısı, ofis/şube yaygınlığı, kurumsal varlık | %20 |
| Kariyer Gelişimi & Eğitim Kültürü | Trainee/rotasyon programları, iç eğitim yatırımı, terfi kültürü | %20 |
| Sektörel Konum | Ulusal veya global ölçekte lider/güçlü oyuncu olma durumu | %15 |
| Kurumsal Stabilite | Kuruluş yılı, operasyonel süreklilik sinyalleri | %10 |
| Dış Sinyaller | Erişilebilir çalışan yorumu/algı sinyalleri (varsa) | %10 |

### 12.2 Skor Bantları

| Bant | Yorum |
|---|---|
| 80-100 | Excellent — öncelikli |
| 60-79 | Good |
| 40-59 | Average / Caution |
| 0-39 | Low — varsayılan olarak dışlanır |

### 12.3 Dışlama Mantığı

- Varsayılan minimum **Company Quality Score eşiği: 50** (konfigüre edilebilir).
- Şirket hakkında yeterli veri bulunamıyorsa (çok yeni/bilinmeyen şirket), skor **"Unrated"** olarak işaretlenir ve sessizce dışlanmak yerine kullanıcının görebileceği ayrı bir alanda tutulur (bkz. Section 20).
- Sistem şu şirket profillerini düşük puanlama eğilimindedir: çok küçük ölçekli, güven vermeyen, kariyer gelişimi zayıf, yeni kurulmuş ve tanınmayan şirketler.
- **Unrated şirketin AI Match Score'a katkısı:** Bir şirket "Unrated" olduğunda, Section 13.1'deki "Company Quality Contribution" bileşeni hesaplamadan çıkarılır ve kalan bileşenlerin ağırlıkları kendi aralarında orantılı olarak yeniden normalize edilir (bileşen sıfır veya nötr bir değer olarak varsayılmaz). Bu, "Unrated" bir şirketin haksız yere ne cezalandırılmasını ne de ödüllendirilmesini sağlar.

### 12.4 Skor Yeniden Kullanımı (Caching)

- Bir şirket için hesaplanan Company Quality Score, `Last Evaluated Timestamp` konfigüre edilebilir bir tazelik penceresinin (varsayılan: **30 gün**, bkz. Section 17) içindeyse yeniden hesaplanmaz; mevcut skor ve alt boyut kırılımı doğrudan yeniden kullanılır.
- Bu mekanizma, aynı şirketin birden fazla açık ilanı olduğunda tekrar eden puanlama maliyetini önler (bkz. NFR-9, FR-6, FR-18).
- **Çok-kullanıcılı önbellekleme kuralı:** Bir şirketin skoru yalnızca **sistem varsayılan ağırlık profiliyle** hesaplandıysa hesaplar arası paylaşılabilir. Bir kullanıcı Section 12.1'deki ağırlıkları kendine özgü şekilde değiştirdiyse, o kullanıcı için ayrı bir skor kaydı tutulur; bu, gelecekte farklı kullanıcıların farklı ağırlıklarla aynı şirkete farklı meşru skorlar vermesine izin verirken, sistem varsayılanını kullanan çoğunluk için önbellekleme kazanımını korur (bkz. Section 15.0, NFR-15). Önbellek anahtarı **Company ID + Weight Profile ID + Rubric Version** üçlüsüdür — Rubric Version, puanlama mantığının (ağırlıklar veya ilgili prompt şablonu) hangi sürümüyle hesaplandığını belirtir; sistem varsayılan ağırlıkla hesaplanan skorlar için sistem genelindeki paylaşılan sürüm numarası, hesaba özel ağırlıkla hesaplanan skorlar için o hesabın kendi config version'ı kullanılır. Bu, sistem varsayılan puanlama mantığı (örn. Section 12.1 ağırlıkları veya company scoring prompt'u) değiştiğinde eski skorların önbellekten yanlışlıkla yeniden kullanılmasını engeller (bkz. FR-6, FR-18, NFR-12).

---

## 13. AI Matching Logic

Her ilan, kullanıcı profiliyle karşılaştırılarak bir **AI Match Score** (0-100) alır. Bu skor her zaman bir **gerekçe listesiyle** birlikte sunulur — skor gerekçesiz sunulmaz.

### 13.1 Skor Kompozisyonu (Varsayılan, Konfigüre Edilebilir Ağırlıklar)

| Bileşen | Açıklama | Varsayılan Ağırlık |
|---|---|---|
| Department/Role Relevance | Section 11.2'deki semantik departman eşleşme skoru | %35 |
| Experience Level Fit | Deneyim seviyesi uyumu | %15 |
| Location Fit | Lokasyon uyumu | %10 |
| Company Quality Contribution | Section 12'deki Company Quality Score'un katkısı | %25 |
| Career Goal Alignment | Kullanıcının kariyer hedefi/anlatısıyla semantik uyum | %15 |

> **Not:** Şirket "Unrated" olduğunda "Company Quality Contribution" bileşeni hesaplamadan çıkarılır ve kalan bileşenlerin ağırlıkları orantılı olarak yeniden normalize edilir; ayrıntı için bkz. Section 12.3.

### 13.2 Açıklanabilirlik (Explainability) Gereksinimi

Her ilan için üretilen gerekçe, kullanıcının kolayca doğrulayabileceği kısa maddeler halinde sunulur. Gerekçe maddeleri her zaman sistemin hesapladığı somut skor bileşenlerine (lokasyon eşleşmesi, deneyim seviyesi, departman skoru, Company Quality Score, kariyer hedefi uyumu) dayanır; serbest, doğrulanamayan yorum içeren maddeler üretilmez (bkz. FR-7, RISK-10). Örnek:

> **Selected because:**
> - Matches preferred department (Business Development)
> - Matches experience level (Entry Level)
> - Located in Istanbul
> - Prestigious employer (Company Quality Score: 88)
> - Aligned with stated career goals

### 13.3 Eşikler

- **Minimum AI Match Score (rapora dahil olmak için): 60** (varsayılan, konfigüre edilebilir). Bu eşiğin altındaki ilanlar, filtrelerden geçmiş olsa bile rapora dahil edilmez.
- **Top Matches:** Şu anda açık/aktif olan ilanlar arasından AI Match Score'a göre sıralanmış ilk 10 ilan.
- **Tutarlılık:** Aynı ilan/profil kombinasyonu, art arda çalıştırmalarda büyük ölçüde tutarlı bir skor üretmelidir (bkz. NFR-12). Bunun asgari güvencesi olarak **içeriği değişmemiş bir ilan yeniden skorlanmaz** (bkz. FR-18) — böylece tutarlılık, gereksiz yeniden skorlama kaynağında önlenerek güvence altına alınır. Tek bir skorlama çağrısı içindeki model determinizmi (örn. sıcaklık/parametre seçimi) teknik tasarım aşamasının sorumluluğudur.

---

## 14. Scheduling

- **Varsayılan çalışma sıklığı:** İki günde bir (48 saat).
- **Zamanlama Sapması (Jitter):** Otomatik çalıştırmalar, tam olarak sabit bir periyotta değil, konfigüre edilebilir küçük bir rastgele sapmayla (varsayılan: ±30 dakika — bkz. Section 17) tetiklenir; bu, tamamen periyodik ve öngörülebilir bot davranışının otomasyon tespiti riskini artırmasını önlemeyi amaçlar (bkz. RISK-1, NFR-14).
- **Manuel tetikleme:** Kullanıcı istediği an sistemi elle çalıştırabilir; bu, otomatik çizelgeyi değiştirmez veya sıfırlamaz — iki mekanizma birbirinden bağımsız çalışır.
- **Çakışma Önleme:** Bir çalıştırma devam ederken yeni bir çalıştırma (otomatik veya manuel) başlatılmaz; bu durum kullanıcıya açıkça bildirilir.
- **Yapılandırılabilirlik:** Çalışma sıklığı sabit kodlanmış bir değer değil, bir konfigürasyon parametresidir (bkz. Section 17).
- **Hata Durumunda Davranış:** Bir çalıştırma (örn. oturum hatası nedeniyle) başarısız olursa, bu durum çalıştırma kaydına (FR-15) işlenir; sistem sessizce bir sonraki döngüyü beklemez, hata görünür kalır.

---

## 15. Data Model

Bu bölüm, sistemin ihtiyaç duyduğu temel veri varlıklarını (entity) kavramsal düzeyde tanımlar. Somut şema/teknoloji seçimi (veritabanı, dosya biçimi vb.) bu dokümanın kapsamı dışındadır.

### 15.0 Multi-Tenant Kapsamlama İlkesi (Mimari Not)

V1 tek bir kullanıcı/hesapla çalışsa da, veri modeli baştan itibaren bir **User/Account ID** kavramı etrafında tasarlanır; V1'de bu kimliğin tek bir değeri olur, ancak alan şemadan hiçbir zaman çıkarılmaz. Varlıklar iki kategoriye ayrılır:

- **Hesaba özel (Account-Scoped) varlıklar** — her biri bir User/Account ID'ye bağlıdır ve kullanıcılar arasında paylaşılmaz: User Profile (15.1), Evaluated Job'ın kullanıcıya özgü kısmı (AI Match Score, Match Rationale, Status — 15.4), Report (15.5), Run Log (15.6) ve tüm konfigürasyon (Section 17.1).
- **Paylaşılabilir/Referans (Shared/Reference) varlıklar** — bir kullanıcıya değil gerçek dünyadaki ilana/şirkete aittir ve birden fazla hesap arasında güvenle paylaşılıp yeniden kullanılabilir: Job Posting (15.2) ve Company Profile (15.3, yalnızca sistem varsayılan ağırlıklarıyla puanlandığında — bkz. Section 12.4).

Bu ayrım, çok-kullanıcılı geçişte veri modelinin yeniden tasarlanmasını gerektirmez — yalnızca aynı şemaya yeni User/Account kayıtları eklenir.

### 15.1 User Profile

| Alan | Açıklama |
|---|---|
| Career Goals | Kullanıcının kariyer hedeflerini özetleyen serbest metin |
| Target Departments | Section 11.2'deki konfigüre edilebilir departman listesi |
| Target Locations | Section 11.1'deki konfigüre edilebilir lokasyon listesi |
| Target Experience Levels | Section 11.3'teki konfigüre edilebilir seviye listesi |
| Skills / Background Summary | Kullanıcının profil özeti |
| Preferences / Dealbreakers | Ek tercihler (varsa); dışlanacak şirket ve/veya ilan listesini (blacklist) de içerir (bkz. FR-19) |

**Not (versiyonlama):** Target Departments, Target Locations ve Target Experience Levels, kavramsal olarak User Profile'a ait olsa da, Section 17'deki diğer parametrelerle **aynı versiyonlanmış konfigürasyon profilinde** saklanır (bkz. Section 17.1) — ayrı, versiyonsuz bir kayıt olarak tutulmazlar. Bu, bu alanlardaki bir değişikliğin de Report'un Config Snapshot Reference'ı (bkz. Section 15.5) tarafından yakalanmasını garanti eder.

### 15.2 Job Posting (Ham / Toplanan Veri)

| Alan | Açıklama |
|---|---|
| Job ID | LinkedIn ilan kimliği (benzersiz) |
| Title | İlan başlığı |
| Company Name / Company ID | Şirket adı ve kimliği |
| Location | Lokasyon metni |
| Workplace Type | On-site / Hybrid / Remote |
| Posted Date | Yayın tarihi |
| Description | İlan açıklama metni |
| Employment Type | Tam zamanlı / Stajyer vb. |
| Easy Apply | Boolean |
| Application URL | Başvuru linki |
| Collected Timestamp | Sistem tarafından toplanma zamanı |

### 15.3 Company Profile

| Alan | Açıklama |
|---|---|
| Company ID / Name | Şirket kimliği ve adı |
| Industry | Sektör |
| Employee Count Range | Çalışan sayısı aralığı |
| Founded Year | Kuruluş yılı |
| Company Quality Score | 0-100 toplam skor |
| Score Breakdown | Section 12.1'deki boyutlara göre alt skorlar |
| Last Evaluated Timestamp | Son değerlendirme zamanı |

### 15.4 Evaluated Job (Skorlanmış Kayıt)

| Alan | Açıklama |
|---|---|
| Job Posting Reference | İlgili Job Posting kaydı |
| Company Profile Reference | İlgili Company Profile kaydı |
| AI Match Score | 0-100 |
| Match Rationale | Gerekçe madde listesi |
| Department Cluster | Normalize edilmiş departman kümesi |
| Filter Result Detail | Hangi filtrelerden geçtiği/geçmediği |
| Status | New / Seen / Updated / Closed |
| First Seen Date / Last Seen Date | İlk ve son görülme tarihleri |
| Report Appearances Count | Kaç raporda göründüğü |

### 15.5 Report

| Alan | Açıklama |
|---|---|
| Report ID | Benzersiz kimlik |
| Generation Date | Oluşturulma tarihi |
| Included Job IDs | Rapora dahil edilen ilanlar |
| Top Matches List | İlk 10 ilan listesi |
| Format | V1: Markdown |
| Config Snapshot Reference | Raporun üretildiği anda yürürlükte olan konfigürasyon setinin sürüm/referans bilgisi (bkz. Section 17, FR-17) |
| Storage Path / File Reference | Bu rapora ait kalıcı, üzerine yazılmayan dosya referansı (bkz. FR-17) |

### 15.6 Run Log (Execution History)

| Alan | Açıklama |
|---|---|
| Run ID | Benzersiz kimlik |
| Trigger Type | Scheduled / Manual |
| Start / End Timestamp | Başlangıç ve bitiş zamanı |
| Jobs Collected / Filtered / New / Closed Counts | Sayısal özet |
| Status | Success / Partial / Failed |
| Error Detail | Varsa hata bilgisi |

### 15.7 İlişkiler (Entity Relationships)

- **Company Profile** (1) → (N) **Job Posting**
- **Job Posting** (1) → (1) **Evaluated Job**
- **Evaluated Job** (N) → (N) **Report** (bir ilan, açık kaldığı sürece — özellikle Top Matches aracılığıyla — birden fazla raporda referans alınabilir)
- **Run Log** (1) → (1) **Report** (Success veya Partial ile sonuçlanan her çalıştırma bir rapor üretir; yeni/güncellenmiş içerik yoksa dahi EDGE-7'de tanımlanan hafif özet raporu üretilir — rapor üretimi hiçbir koşulda tamamen atlanmaz)

---

## 16. Reporting Format

Rapor **departman bazında gruplanır** ve ayrıca bir **Top Matches** bölümü içerir. V1'de çıktı formatı **Markdown**'dır.

### 16.1 Rapor Yapısı (Üstten Alta)

1. Özet başlık (çalıştırma tarihi, toplam yeni ilan sayısı)
2. **Top Matches** (AI Match Score'a göre sıralı ilk 10 ilan — açık kalan en iyi fırsatların anlık görüntüsü; daha önce raporlanmış ama hâlâ güçlü ve açık olan ilanlar burada tekrar görünebilir, açıkça "Previously Reported" olarak işaretlenerek)
3. Departman bazlı bölümler (sadece **NEW** ve **UPDATED** ilanlar — daha önce değişmeden raporlanmış ilanlar bu bölümlerde tekrar gösterilmez)
4. Çalıştırma özeti / meta bilgi (isteğe bağlı alt bilgi)

Her rapor, önceki raporların üzerine yazılmayan, kendi kimliğine sahip ayrı bir dosya olarak kalıcı hale getirilir (bkz. FR-17); bu sayede "Previously Reported" etiketlemesi geçmiş rapor kayıtlarına dayanarak doğrulanabilir. Sistemin ilk çalıştırmasında üretilen rapor, normal akış yerine Bootstrap davranışını izler (bkz. FR-20).

### 16.2 Örnek Rapor İskeleti (İllüstratif)

```markdown
# Job Report — 2026-08-07

## Top Matches

1. [NEW] Business Development Executive — Örnek A.Ş. (AI Match: 92 / Company Quality: 85)
2. ...

## Business Development

### [NEW] Business Development Executive — Örnek A.Ş.
- Lokasyon: İstanbul (Hybrid)
- Yayın Tarihi: 2026-08-05
- AI Match Score: 92 / 100
- Company Quality Score: 85 / 100
- Easy Apply: Evet
- Başvuru Linki: [link]

Selected because:
- Matches preferred department
- Matches experience level
- Located in Istanbul
- Prestigious employer
- High career potential

## Strategy
...

## Marketing
...

## Consulting
...
```

### 16.3 Etiketleme Kuralları

| Etiket | Anlamı |
|---|---|
| **NEW** | İlk kez görülen ilan |
| **UPDATED** | Anlamlı içerik değişikliği tespit edilen, önceden görülmüş ilan |
| (Etiketsiz, sadece Top Matches içinde) | Önceden raporlanmış ama hâlâ güçlü ve açık olan ilan |

### 16.4 Duplicate & Closed Kuralları

- Aynı ilan, içerik değişmediyse bir kez raporlanır; departman bölümlerinde tekrar görünmez.
- Kapanmış ilanlar hiçbir bölümde (Top Matches dahil) gösterilmez.
- İlan güncellenmişse (bkz. FR-14), yalnızca güncellenme durumu belirtilir; ilan sıfırdan yeni gibi sunulmaz.
- Top Matches bölümünde etiketsiz olarak tekrar görünen, hâlâ açık ve güçlü bir ilan (bkz. Section 16.3), Section 5'teki Duplicate Rate metriği kapsamında **duplicate sayılmaz** — bu metrik yalnızca bir ilanın NEW etiketiyle birden fazla kez görünmesini kapsar.

---

## 17. Configuration

Aşağıdaki kriterlerin **kod değişikliği gerektirmeden** güncellenebilmesi V1 için zorunludur (bkz. FR-13, NFR-6).

| Parametre | Varsayılan Değer | Örnek Değişiklik |
|---|---|---|
| Target Location(s) | İstanbul | İstanbul → Ankara |
| Target Departments | Section 11.2 listesi | Yeni bir küme/unvan eklenmesi |
| Target Experience Levels | Section 11.3 listesi | "Junior" çıkarılması |
| Department Match Confidence Eşiği | 0.65 (bkz. Section 11.2) | 0.65 → 0.75 |
| Company Quality Score Eşiği | 50 | 50 → 65 |
| AI Match Score Eşiği | 60 | 60 → 70 |
| Borderline Bant Genişliği | 5 puan, eşiğin altı (bkz. FR-16) | 5 → 8 |
| Schedule Interval | 2 gün | 2 gün → 3 gün |
| Schedule Jitter | ±30 dakika (bkz. Section 14) | ±30 → ±60 |
| Top Matches Sayısı | 10 | 10 → 15 |
| Company Score Re-evaluation Window | 30 gün (bkz. Section 12.4) | 30 → 60 |
| Max Jobs / Pages per Run | 200 ilan (bkz. FR-21) | 200 → 100 |
| Excluded Companies / Jobs (Blacklist) | Boş liste (bkz. FR-19) | Bir şirket adı veya Job ID eklenmesi |

**Tasarım prensibi:** Konfigürasyon ve iş mantığı birbirinden ayrıştırılmalıdır — bir filtre kriterinin değişmesi, sistemin başka hiçbir bileşeninde değişiklik gerektirmemelidir. Konfigürasyon insan tarafından okunabilir/düzenlenebilir şekilde tutulmalı ve değişiklik geçmişi (hangi kriter ne zaman değişti) izlenebilir olmalıdır — bu, geçmiş raporların hangi kriterlerle üretildiğini anlamayı sağlar. Geçersiz veya şema dışı bir konfigürasyon değişikliği (örn. toplamı %100 etmeyen skor ağırlıkları, tanımsız bir departman kümesi referansı) çalıştırma başlamadan reddedilir (bkz. FR-13, EDGE-15). Her Report, üretildiği andaki konfigürasyon setinin bir referans/sürüm bilgisini taşır (bkz. Section 15.5), böylece geçmiş bir raporun hangi kriterlerle üretildiği sonradan da doğrulanabilir.

### 17.1 Konfigürasyonun Kapsamı ve Kullanıcı İzolasyonu (Mimari Gereksinim)

Yukarıdaki tablodaki tüm parametreler — ve aşağıda listelenen ek parametreler — **iş mantığından tamamen izole, kullanıcı/hesap bazlı bir konfigürasyon profiline** aittir; hiçbiri kod içine veya iş mantığı katmanına gömülmez. V1'de tek bir konfigürasyon profili (tek kullanıcı) bulunur, ancak profil şeması baştan itibaren bir User/Account ID ile ilişkilendirilir; böylece ikinci bir kullanıcının eklenmesi yeni bir profil kaydı oluşturmaktan ibarettir, iş mantığında değişiklik gerektirmez (bkz. NFR-15, Section 15.0).

**Ek olarak konfigüre edilebilir olması gereken parametreler:**

| Parametre | Varsayılan Değer | Not |
|---|---|---|
| AI Match Score Bileşen Ağırlıkları | Section 13.1 tablosu | Toplamı %100 olmalı (bkz. FR-13 doğrulama kuralı) |
| Company Quality Score Boyut Ağırlıkları | Section 12.1 tablosu | Toplamı %100 olmalı (bkz. FR-13 doğrulama kuralı) |
| LLM Prompt Şablonları (Department Matching, AI Match Rationale, Company Scoring) | Sistem varsayılan şablonları | Kullanıcı diline/üslubuna göre özelleştirilebilir; şablon değişikliği skor tutarlılığını etkileyebileceğinden bir Config Version artışı tetikler (bkz. NFR-12) |
| Notification Settings | Devre dışı (V1'de aktif bildirim kanalı yok — bkz. Section 18 Phase 2) | V1'de kullanılmasa da konfigürasyon şeması Phase 2 bildirim kanalları için şimdiden ayrılır; sonradan ayrı bir alt sistem olarak eklenmez |
| Report Format / Template | V1: Markdown, sabit şablon (Section 16.2) | Format ve şablon, gelecekte kullanıcı bazlı özelleştirmeye (örn. farklı diller, farklı gruplama) açık olacak şekilde konfigürasyondan okunur, koda gömülmez |

**Kullanıcı izolasyonu ilkesi:** Filtreleme, skorlama ve raporlama motorları (bkz. Section 21 "Modular Pipeline Architecture") hiçbir zaman "kullanıcının" kim olduğuna dair gömülü bir varsayımla çalışmaz; her çalıştırma, hangi kullanıcı/hesap için çalıştığını ve o hesaba ait konfigürasyon profilini bir girdi olarak alır. Bu, motorun kendisini değiştirmeden aynı çalıştırma mantığının farklı bir konfigürasyon profiliyle (yani farklı bir kullanıcı için) tekrar kullanılabilmesini sağlar.

---

## 18. Future Roadmap

Bu bölümdeki tüm özellikler **V1 kapsamı dışındadır**. Roadmap, mantıksal bağımlılıklara göre fazlara ayrılmıştır.

> **Not:** Company Quality Score ve AI Match Score, kullanıcının orijinal özellik listesinde burada da anılmış olsa da, bu iki yetenek zaten **V1'in zorunlu bir parçasıdır** (bkz. Section 12 ve Section 13). Burada yalnızca referans amacıyla belirtilmiştir; roadmap'te tekrar "yeni" özellik olarak sayılmamıştır.

### Phase 2 — Career Intelligence Enhancements

*Amaç: keşif katmanının üzerine, başvuru kararını güçlendiren zeka katmanı eklemek.*

| Özellik | Açıklama |
|---|---|
| AI Job Summary | Her ilanın 5-6 satırlık özetinin çıkarılması |
| Company Intelligence | Şirket hakkında kısa özet: sektör, çalışan sayısı, kültür, avantajlar, neden iyi bir şirket olduğu |
| Skill Gap Analysis | İlanda istenen ancak kullanıcıda bulunmayan yeteneklerin analizi |
| Salary Estimation | Mümkün olduğunda maaş tahmini |
| Personal Dashboard | Kaç ilana bakıldığı, kaçına başvurulduğu, ortalama AI Match Score, başvuru başarı oranı, en çok ilan gelen departmanlar, haftalık istatistikler |
| Notification System | Yeni yüksek kaliteli ilan bulunduğunda Telegram, Discord, Slack, WhatsApp veya Email üzerinden bildirim |
| Ek Çıktı Entegrasyonları | Notion Database, Google Sheets, Airtable, PDF, Email Report, Telegram Message, Discord Message |

### Phase 3 — Application Enablement

*Amaç: doğru ilanı bulmaktan, o ilana en iyi şekilde başvurmaya geçiş. Bu faz, kullanıcı onayına dayalı (human-in-the-loop) eylemler içerir.*

| Özellik | Açıklama |
|---|---|
| CV Optimization | Her ilana göre CV'nin optimize edilmesi |
| Cover Letter Generation | Her ilan için otomatik cover letter oluşturulması |
| Automatic Easy Apply | Kullanıcının onayıyla uygun ilanlara otomatik başvuru |
| Application Tracker | Başvuru durumu takibi: Applied, Interview, HR Interview, Technical Interview, Assessment, Offer, Rejected |

### Phase 4 — Career Growth & Advisory

*Amaç: sistemi, tekil başvuru döngüsünün ötesinde bir kariyer danışmanına dönüştürmek.*

| Özellik | Açıklama |
|---|---|
| AI Career Advisor | Kariyer tavsiyeleri sunulması |
| Interview Preparation | Başvurulan şirkete özel mülakat hazırlığı |
| Career Trend Analysis | Hangi yeteneklerin en çok arandığının analizi (geçmiş veriye dayanır — bkz. NFR-11) |

**Fazlar arası bağımlılık notu:** Application Tracker'ın anlamlı olabilmesi için önce bir başvuru kaydı mekanizmasının var olması gerekir; Interview Preparation, Application Tracker'daki "Interview" durumuna bağlıdır; Automatic Easy Apply, CV Optimization'ın olgunlaşmasından önce devreye alınmamalıdır (optimize edilmemiş bir CV ile otomatik başvuru, kalite hedefiyle çelişir).

---

## 19. Risks

| ID | Kategori | Risk | Etki | Azaltma (Mitigation) |
|---|---|---|---|---|
| RISK-1 | Platform / Compliance | LinkedIn'in kullanım şartları otomasyonu/scraping'i kısıtlar; hesap kısıtlanabilir/işaretlenebilir | Yüksek — hesap erişiminin kaybı, tüm sistemin durması | Muhafazakâr çalışma sıklığı, sabit periyoda küçük bir zamanlama sapması (jitter) eklenmesi (bkz. Section 14, NFR-14), V1'de salt okunur işlemler (otomatik başvuru yok), hesap sağlığının periyodik izlenmesi |
| RISK-2 | Data Reliability | LinkedIn arayüz/yapı değişiklikleri veri toplamayı bozabilir | Orta — sessiz veri kaybı riski | Çalıştırma kayıtlarında anomali izleme (örn. beklenmedik sıfır sonuç) |
| RISK-3 | AI Scoring Reliability | AI skorlama motoru tutarsız veya hatalı gerekçeler üretebilir | Orta — güven kaybı | Zorunlu gerekçe şeffaflığı (FR-7), periyodik manuel kalibrasyon kontrolü |
| RISK-4 | False Negative (Sessiz Kayıp) | Aşırı sıkı filtreler, kullanıcının hiç görmediği iyi fırsatları eleyebilir | Yüksek — görünmez olduğu için fark edilmesi zor | Borderline review bucket (FR-16), periyodik manuel örnekleme kontrolü |
| RISK-5 | Company Scoring Subjectivity | Prestij/kalite algısı özneldir; rubrik kullanıcının gerçek tercihiyle örtüşmeyebilir | Orta | Konfigüre edilebilir ağırlıklar (Section 12.1), zamanla geri bildirime göre ayarlama |
| RISK-6 | Data Privacy & Security | LinkedIn kimlik bilgileri ve kişisel profil verisi saklanır | Yüksek | Güvenli kimlik bilgisi saklama pratikleri (teknik tasarım aşamasında detaylandırılacak) |
| RISK-7 | Single Point of Failure | Tek kullanıcı/tek sistem; yedekleme veya ekip desteği yok | Orta | Minimum çalıştırma günlüğü (FR-15) ile sessiz arızaların erken fark edilmesi; çalıştırma yarıda kesilirse Job History Store'un tutarsız durumda kalmaması (bkz. NFR-13) |
| RISK-8 | Scope Creep | Geniş roadmap, V1'in güvenilir teslimatını geciktirebilir | Orta | Sıkı faz kapılama (Section 18), V1 kapsamının bu dokümanla sabitlenmesi |
| RISK-9 | Cost Escalation | AI/LLM kullanım maliyeti, ilan hacmi ve roadmap özellikleriyle (CV, cover letter) birlikte artabilir | Orta | Maliyet izleme (NFR-9), filtre sıralamasının AI çağrısından önce uygulanması (Section 11.4), skor önbellekleme (bkz. FR-6, FR-18) |
| RISK-10 | AI Hallucination in Rationale | LLM, skor bileşenleriyle desteklenmeyen, uydurma veya yanıltıcı bir gerekçe/nitelendirme üretebilir (örn. "Unrated" bir şirketi "prestigious" olarak nitelendirmek) | Orta — açıklanabilirlik ilkesini (Section 3) ve kullanıcı güvenini zedeler | Gerekçe maddelerinin yalnızca yapısal skor bileşenlerinden üretilmesi zorunluluğu (bkz. FR-7, Section 13.2); serbest metin yorum üretimine izin verilmemesi |

---

## 20. Edge Cases

| ID | Senaryo | Önerilen Davranış |
|---|---|---|
| EDGE-1 | İlanda deneyim seviyesi açıkça etiketlenmemiş | İçerikten AI çıkarımı yapılır; çıkarım güven skoru düşükse borderline bucket'a alınır (elenmez) |
| EDGE-2 | İlan başlığı sadece Türkçe ve listede birebir karşılığı yok | Semantik eşleştirme İngilizce-Türkçe iki dilli çalışmalıdır (bkz. Section 11.2) |
| EDGE-3 | Uzaktan ilan, hiçbir şehir/ülke bilgisi içermiyor | Varsayılan olarak dışlanır; ayrı bir "Location Unclear" alanında işaretlenir, sessizce silinmez |
| EDGE-4 | Şirket hakkında hiçbir veri bulunamıyor (çok yeni/bilinmeyen şirket) | Company Quality Score "Unrated" olarak işaretlenir; otomatik dışlama yerine kullanıcıya görünür bir "Unrated" alanına düşer |
| EDGE-5 | Kapanmış bir ilan daha sonra yeniden aktif hale geliyor | Aynı Job ID ile yeniden açılırsa **NEW** olarak yeniden değerlendirilir |
| EDGE-6 | İlanda sadece kozmetik bir değişiklik var (örn. yazım düzeltmesi) | **UPDATED** etiketi tetiklenmez; yalnızca unvan, seviye, lokasyon veya açıklamada anlamlı değişiklik bu etiketi tetikler |
| EDGE-7 | Bir çalıştırma döngüsünde hiç yeni ilan bulunamıyor | Rapor tamamen bastırılmaz; "Bu döngüde yeni eşleşen ilan bulunamadı" özetiyle hafif bir rapor üretilir (sistemin çalıştığına dair güven sağlar) |
| EDGE-8 | Aynı şirketin neredeyse birebir aynı birden fazla ilanı | Tam kimlik eşleşmesinin yanında başlık+şirket+lokasyon bazlı yakın-kopya (near-duplicate) tespiti uygulanır; raporda tekilleştirilir |
| EDGE-9 | Çalıştırma sırasında LinkedIn geçici olarak sınırlama uyguluyor (rate limiting) | Kısmi veri "tam sonuç" gibi sunulmaz; çalıştırma "Partial" olarak işaretlenir (bkz. Section 15.6) |
| EDGE-10 | Kullanıcı çalıştırmalar arasında filtre kriterini değiştiriyor (örn. İstanbul → Ankara) | Değişiklik yalnızca ileriye dönük uygulanır; geçmiş veriler otomatik yeniden değerlendirilmez (davranış öngörülebilir kalır) |
| EDGE-11 | AI Match Score, dışlama eşiğine çok yakın (örn. eşik 60 iken skor 58) | Sert kesim yerine borderline bucket'a alınır (bkz. FR-16, RISK-4) |
| EDGE-12 | İlan başlığı ile açıklama metni arasında çelişkili kıdem sinyali var (örn. başlık "Junior", açıklama "5+ years") | Açıklama metnindeki sinyal esas alınır (bkz. FR-5, Section 11.3) |
| EDGE-13 | Sistem ilk kez çalışıyor (Job History Store boş) | Sonuçlar normal "NEW" akışı yerine açıkça işaretlenmiş bir Bootstrap/İlk Tarama bölümünde sunulur (bkz. FR-20) |
| EDGE-14 | Bir çalıştırma pipeline'ın ortasında (örn. Company Scoring ile AI Matching arasında) kesintiye uğruyor | Job History Store yarım kalan adımdan güncellenmez; bir sonraki çalıştırma tutarlı bir durumdan devam eder (bkz. NFR-13) |
| EDGE-15 | Kullanıcı konfigürasyonu geçersiz/şema dışı bir değerle güncelliyor (örn. ağırlıklar toplamı %100 değil) | Çalıştırma başlamadan reddedilir ve hata açıkça raporlanır; sistem geçersiz konfigürasyonu sessizce görmezden gelip varsayılana dönmez (bkz. FR-13) |

---

## 21. Technical Considerations

Bu bölüm, teknik tasarım aşamasına girdi sağlayacak mimari prensipleri **araç/platform bağımsız** şekilde özetler. Somut platform, node/adım yapısı ve kod bu PRD'nin kapsamı dışındadır.

- **Authentication Strategy:** LinkedIn'e kişisel hesap üzerinden oturum tabanlı erişim gerekir; oturum süresi dolabileceğinden yeniden kimlik doğrulama/uyarı akışı tasarlanmalıdır.
- **State Persistence:** Duplicate/Closed/New tespiti çalıştırmalar arası kalıcı durum gerektirir; sistem **stateless** tasarlanamaz — kalıcı bir "Job History Store" mimarinin merkezinde olmalıdır.
- **AI/LLM Integration:** Semantik departman eşleştirme, şirket puanlama desteği ve AI Match Score/gerekçe üretimi için bir dil modeli entegrasyonu gerekir; maliyet, gecikme ve skor tutarlılığı (bkz. NFR-12) teknik tasarımda ele alınmalıdır.
- **Rate Limiting & Throttling:** Platform riskini azaltmak ve hesap sağlığını korumak için veri toplama adımlarının hızı sınırlandırılmalı, ani/yoğun istek patlamalarından kaçınılmalıdır.
- **Modular Pipeline Architecture:** Collection → Filtering → Scoring → Reporting katmanları birbirinden ayrıştırılmalı; böylece Section 18'deki her yeni özellik çekirdek keşif mantığını yeniden yazmadan eklenebilir.
- **Multi-Tenant-Ready Architecture (Single-Tenant Deployment for V1):** İş mantığı katmanları (Filtering, Scoring, Reporting) hiçbir kullanıcıya özgü veri veya tercihi doğrudan içermez; bunun yerine her çalıştırma bir (User/Account ID, Config Profile) çiftini girdi olarak alır. V1 bu modeli tek bir hesapla çalıştırır, ancak ikinci bir hesabın eklenmesi yeni bir konfigürasyon/veri kaydından ibarettir — çekirdek motorun değişmesini gerektirmez (bkz. NFR-15, Section 1 "Mimari Not", Section 15.0, Section 17.1).
- **Config/Business-Logic Separation:** Filtreler, skorlama ağırlıkları, LLM prompt şablonları, çizelgeleme, bildirim ayarları ve rapor formatı dahil hiçbir kullanıcı tercihi kod içine sabitlenmez (hardcode edilmez); tamamı çalışma zamanında bir konfigürasyon katmanından okunur (bkz. Section 17.1).
- **Idempotency:** Aynı döngünün (örn. manuel tetikleme + hemen ardından planlanan çalıştırma) art arda çalışması, tekrar eden rapor girdileri veya bozuk durum üretmemelidir.
- **Run Atomicity / Crash Recovery:** Pipeline'ın herhangi bir adımda (örn. Collection tamamlandı ama State Update tamamlanmadı) kesintiye uğraması, Job History Store'u tutarsız bir ara durumda bırakmamalıdır; bir çalıştırma ya bütünüyle durum değişikliklerini uygular ya da hiçbirini uygulamaz (bkz. NFR-13, EDGE-14).
- **Evaluation Caching Layer:** Company Quality Score ve AI Match Score hesaplamaları, içerik/tazelik bazlı bir önbellekleme katmanı üzerinden yeniden kullanılabilir olmalıdır (bkz. FR-6, FR-18, Section 12.4); bu, hem maliyet (NFR-9) hem de skor tutarlılığı (NFR-12) hedeflerini destekler.
- **Configuration Validation:** Konfigürasyon, sisteme yüklenmeden önce şema/tutarlılık doğrulamasından geçmelidir (bkz. FR-13); geçersiz konfigürasyon çalıştırmayı başlatmadan engellenmelidir.
- **Observability:** Minimum düzeyde çalıştırma günlüğü (başarı/başarısızlık, sayılar) V1'den itibaren zorunludur; aksi halde oturum süresi dolması gibi sessiz arızalar fark edilmeyebilir.
- **Data Retention Strategy:** Kapanmış/geçmiş ilan ve şirket verisi silinmemelidir; bu veri, henüz V1'de kullanılmasa da Career Trend Analysis (Phase 4) gibi gelecekteki özellikler için gerekli geçmiş temelini oluşturur.
- **Portability:** Konfigürasyon ve veri modeli, ileride otomasyon platformu değişse bile geçmiş veri ve ayarların taşınabilmesini sağlayacak kadar platform-bağımsız tutulmalıdır.

---

## 22. Assumptions

| ID | Varsayım |
|---|---|
| ASM-1 | Kullanıcının aktif ve iyi durumda kişisel bir LinkedIn hesabı vardır |
| ASM-2 | V1'de başvurular tamamen kullanıcı tarafından manuel olarak yapılır |
| ASM-3 | V1, tek bir kullanıcı/hesapla dağıtılır ve çalıştırılır; çoklu kullanıcı senaryosu V1 ürün kapsamında değildir (mimari bu senaryoyu engellemez — bkz. Section 1 "Mimari Not", NFR-15) |
| ASM-4 | İlanlar hem Türkçe hem İngilizce olabilir; sistem her ikisini de anlayabilmelidir |
| ASM-5 | Bir AI/LLM sağlayıcısına erişim mevcuttur ve kullanıcı tarafından bütçelenmiştir |
| ASM-6 | Şirket büyüklüğü, sektör gibi veriler LinkedIn şirket sayfalarından/kamuya açık kaynaklardan çıkarılabilir düzeydedir |
| ASM-7 | Kullanıcı, konfigürasyonu (departman, eşik değerleri vb.) zaman zaman gözden geçirip ince ayar yapacaktır; V1'in ilk günden itibaren mükemmel sonuç vermesi beklenmez |
| ASM-8 | Sistem gözetimsiz (unattended) çalışır; kullanıcı raporu eşzamansız olarak inceler, gerçek zamanlı bir sohbet arayüzü V1 kapsamında değildir |
| ASM-9 | Varsayılan iki günlük çalışma sıklığı bir başlangıç noktasıdır; gözlemlenen ilan yayınlanma hızına göre ileride ayarlanabilir |

---

## Appendix A: Glossary

| Terim | Tanım |
|---|---|
| AI Match Score | Bir ilanın kullanıcı profiline uygunluğunu ifade eden 0-100 arası skor (Section 13) |
| Company Quality Score | Bir şirketin kurumsal kalite/prestij düzeyini ifade eden 0-100 arası skor (Section 12) |
| Easy Apply | LinkedIn'in tek tıkla başvuru özelliği |
| Top Matches | AI Match Score'a göre sıralanmış, o anki en iyi 10 açık ilan |
| NEW | İlk kez görülen ilan etiketi |
| UPDATED | Anlamlı içerik değişikliği tespit edilen ilan etiketi |
| Closed Job | Başvuruya kapanmış, artık raporlanmayan ilan |
| Department Cluster | Anlamca yakın unvanların gruplandığı departman kümesi (Section 11.2) |
| Borderline Bucket | Eşik değerine çok yakın skorlu, sert şekilde elenmeyen ilanların tutulduğu ayrı bölüm |
| Run / Execution Cycle | Sistemin tetiklenmesinden rapor üretimine kadar olan tek bir uçtan uca çalıştırma |
| Semantic Matching | Salt kelime eşleşmesinin ötesinde, anlam benzerliğine dayanan eşleştirme |
| Bootstrap Run | Job History Store boşken yapılan, sonuçların "NEW" yerine ayrı bir başlangıç envanteri olarak sunulduğu ilk çalıştırma (bkz. FR-20) |
| Blacklist / Exclusion List | Kullanıcının kalıcı olarak dışladığı şirket veya ilanların listesi (bkz. FR-19) |
| Score Cache / Re-evaluation Window | Bir şirket veya ilanın skorunun yeniden hesaplanmadan önce yeniden kullanılabileceği tazelik süresi (bkz. Section 12.4, FR-18) |
| Run Atomicity | Bir çalıştırmanın durum değişikliklerini ya bütünüyle ya da hiç uygulamaması; kesintiye uğrarsa yarım kalan güncellemenin geçerli olmaması (bkz. NFR-13) |
| Config Snapshot | Bir raporun üretildiği anda yürürlükte olan konfigürasyon setinin referans/sürüm bilgisi (bkz. Section 15.5, Section 17) |
| Account-Scoped Data | Yalnızca bir kullanıcı/hesaba ait, hesaplar arasında paylaşılmayan veri (örn. User Profile, Report, Run Log) (bkz. Section 15.0) |
| Shared / Reference Data | Bir kullanıcıya değil gerçek dünyadaki ilana/şirkete ait, hesaplar arasında paylaşılabilir veri (örn. Job Posting, sistem-varsayılanı ile puanlanmış Company Profile) (bkz. Section 15.0) |
| Config Profile | Bir kullanıcı/hesaba ait tüm filtre, eşik, ağırlık, prompt, çizelge ve format tercihlerini içeren, iş mantığından izole konfigürasyon kümesi (bkz. Section 17.1) |
| Weight Profile | Company Quality Score veya AI Match Score bileşen ağırlıklarının belirli bir kümesi; sistem varsayılanından farklıysa önbellekleme anahtarına dahil edilir (bkz. Section 12.4) |

---

## Appendix B: Version History

| Versiyon | Tarih | Değişiklik |
|---|---|---|
| 1.0 | 2026-08-07 | İlk kapsamlı PRD taslağı oluşturuldu |
| 1.1 | 2026-08-07 | Mimari inceleme sonrası netleştirmeler eklendi: yeni gereksinimler (rapor dosyalarının kalıcı ve ayrı saklanması — FR-17, skor/değerlendirme önbellekleme — FR-18, Section 12.4, şirket/ilan dışlama listesi — FR-19, bootstrap/cold-start davranışı — FR-20, toplama hacmi üst sınırı — FR-21, çalıştırma atomikliği — NFR-13, zamanlama sapması/jitter — NFR-14); belirsizlik giderimleri (departman güven eşiği ve borderline bant genişliği için varsayılan değerler, "Unrated" şirketin AI Match Score'a katkısının yeniden normalize edilmesi, "anlamlı değişiklik" kapsamının somutlaştırılması, çelişkili kıdem sinyali önceliği, Duplicate Rate metriğinin Top Matches ile ilişkisinin netleştirilmesi, konfigürasyon doğrulama ve config-snapshot gereksinimi); yeni risk maddesi (RISK-10 — AI Hallucination in Rationale) ve dört yeni edge case (EDGE-12 — EDGE-15) eklendi. |
| 1.2 | 2026-08-07 | Ticarileştirme/SaaS'a hazır mimari gereksinimi eklendi: Section 1'e yeni "Mimari Not" (multi-tenant hazırlığının bir ürün değil mimari kararı olduğu), Section 3'e yeni tasarım felsefesi ilkesi, Section 4'e yeni uzun vadeli hedef G-10, Section 8'e yeni NFR-15 (Multi-Tenancy Readiness) ve NFR-6/NFR-8'in genişletilmesi, Section 15'e yeni 15.0 alt bölümü (Account-Scoped vs. Shared/Reference varlık ayrımı), Section 12.4 ve FR-18'e çok-kullanıcılı önbellekleme/kapsamlama netleştirmesi (Weight Profile ve User/Account ID'yi içeren önbellek anahtarları), Section 17'ye yeni 17.1 alt bölümü (AI/Company skor ağırlıkları, prompt şablonları, bildirim ayarları, rapor formatı için ek konfigürasyon parametreleri ve kullanıcı izolasyonu ilkesi), Section 21'e Multi-Tenant-Ready Architecture ve Config/Business-Logic Separation ilkeleri, ASM-3'e netleştirme ve Appendix A'ya dört yeni terim (Account-Scoped Data, Shared/Reference Data, Config Profile, Weight Profile) eklendi. |
| 1.3 | 2026-08-07 | Ortak PRD+TDD mimari incelemesinde tespit edilen 5 tutarsızlık çözüldü (kapsam veya yeni özellik değişikliği yok): (1) Section 15.7'deki Run Log→Report kardinalitesi, EDGE-7 ile çelişen (0..1) yerine (1)→(1) olarak düzeltildi ve "rapor üretilmeyebilir" ifadesi kaldırıldı; (2) Section 15.1'e, Target Departments/Locations/Experience Levels'ın Section 17'deki versiyonlanmış konfigürasyon profiliyle aynı yapıda saklandığını ve Config Snapshot tarafından kapsandığını belirten bir versiyonlama notu eklendi; (3) Section 12.4'teki çok-kullanıcılı önbellekleme kuralına, sistem varsayılan puanlama mantığı değiştiğinde eski skorların yeniden kullanılmasını engelleyen bir **Rubric Version** bileşeni eklendi; (4) FR-18'e, önbellek geçerliliğinin FR-14'teki alan kapsamına (Title/Experience Level/Location/Workplace Type/Description) dayandığını ve oynak alanları hariç tuttuğunu belirten bir cümle eklendi. (Beşinci düzeltme — zamanlama/kilit durumu için kalıcı alanlar — yalnızca TDD v1.1'in somut şemasını etkiler, bkz. o doküman.) |
