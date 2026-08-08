"""AccountConfigProfile semasi (TDD Section 15, Roadmap M2.1 "Config Semasi
ve Dogrulama").

Konumlandirma notu: M1.1/M1.3/M1.4'un cesitli docstring'leri "AccountConfigProfile
domain modeli M2.1'de tanimlanacak" diyerek bunun `domain/` altinda
yasayacagini ima etmisti. Bu, o yazilarin kendi ongorusunde kucuk bir
yanlislikti - Roadmap M2.1'in dosya listesi (`config/schema.py`,
`config/validator.py`) ve TDD Section 5'in klasor agaci ACIKCA ve
birbiriyle TUTARLI sekilde bu semanin `config/` altinda yasamasi
gerektigini belirtir. Cakisan bir gereksinim degil, yalnizca erken
yorumlarin duzeltilmesi.

Bu modul, M1.4'un GERCEKTEN urettigi ve `account_config_profiles`'a
yazdigi somut sekli birebir modeller (bkz. cli.py:seed(),
config/system.defaults.yaml, config/accounts/default.account.yaml,
gercek seed edilmis satirin psql cikisi) - M1.4'un onaylanmis veri sekli
DEGISTIRILMEMISTIR (proje talimati geregi); bu modul yalnizca o sekli
dogrulanabilir bir tipe donusturur. Yalnizca JSONB is-konfigurasyonu
icerigi modellenir (target_criteria...prompt_template_refs) - account_id/
config_version/is_active/validated_at gibi sistem-yonetimli bookkeeping
kolonlari zaten db/models.py'de guclu tiplidir ve bu semanin kapsami
disindadir.

`extra="forbid"`: her ic-ice model, M1.3/M1.4 incelemesinde bulunan
sessiz-veri-kaybi hatasindan (CompanyProfile.last_evaluated_timestamp,
Preferences) ders alinarak, FR-13'un "gecersiz veya sema disi bir
konfigurasyon... acikca reddedilir" gereksinimini kod seviyesinde
zorunlu kilar - taninmayan bir anahtar (orn. bir alan adindaki yazim
hatasi) sessizce yutulmaz, aksine acikca reddedilir.

BILINEN, KASITLI OLARAK COZULMEMIS BIR MADDE (proje talimatiyla acikca
onaylanmis bir bosluk): Roadmap M2.1'in "Beklenen Sonuc" satiri acikca
"tanimsiz bir departman referansi" der ("Tamamlanma Dogrulamasi" satiri
ise daha genel "tanimsiz referans" der - Roadmap'in kendi ici bir
tutarsizligi). M1.4'un zaten onaylanmis target_criteria.departments
alani bir REFERANS degil, dogrudan bir TAKSONOMI TANIMIDIR
(cluster_name -> ornek unvanlar) - PRD Section 17'nin kendisi bu alani
acikca genisletilebilir/acik-uclu olarak tanimlar ("Yeni bir kume/unvan
eklenmesi" gecerli bir degisiklik ornegidir). "Tanimsiz bir departman
referansi" kavrami bu yuzden MEVCUT semada dogrulanacak hicbir seye
karsilik gelmez - boyle bir kontrol eklemek ya (a) target_criteria'yi
department_taxonomy + target_departments (secim listesi) olarak yeniden
yapilandirmayi ya da (b) gereksinimin baska bir alana (orn.
experience_levels) uygulanacak sekilde yeniden yorumlanmasini
gerektirirdi. Proje talimati acikca ikisini de yasakladi ("Do not change
M1.4... Do not reinterpret the specification... Do not restructure the
schema unless the specification explicitly requires it"). Bu yuzden bu
spesifik dogrulama KASITLI OLARAK UYGULANMAMISTIR - bkz.
config/validator.py'deki TODO ve tests/unit/config/test_validator.py'deki
acikca isaretlenmis (skip edilmis) test.

Yukaridakinden AYRI, bagimsiz olarak gerekceli iki kapali-kume dogrulamasi
(bir ic-denetimde eksik bulundu, bkz. commit dokumani): `workplace_types`
ve `experience_levels`, "departman referansi" sorusunun bir yeniden
yorumu DEGILDIR - ikisi de kendi baslarina, PRD'nin zaten net bir sekilde
KAPALI kume olarak tanimladigi alanlardir ve M1.4'un verisini hic
degistirmeden dogrulanabilirler:
- `workplace_types`: PRD Section 15.2 zaten tam olarak {On-site, Hybrid,
  Remote} der; bu M1.1'in `domain.job_posting.WorkplaceType` enum'unda
  zaten somutlasmis - burada yeniden tanimlamak yerine DOGRUDAN ICE
  AKTARILIR (db/models.py'nin ORM ENUM sutunlari icin ayni enum'u
  yeniden kullanmasiyla ayni, zaten onaylanmis desen).
- `experience_levels`: PRD Section 11.3 acik bir 8 degerlik liste verir;
  Section 17'nin bu alan icin verdigi TEK degisiklik ornegi CIKARMA
  ("'Junior' cikarilmasi") - hicbir yerde EKLEME ornegi yoktur
  (departments'in "yeni kume eklenmesi" ornegiyle tam ters) - bu, kumenin
  KAPALI oldugunu acikca gosterir.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from linkedinbot.domain.job_posting import WorkplaceType

# PRD Section 11.3: kabul edilen deneyim seviyeleri (kapali kume - Section
# 17'nin tek degisiklik ornegi bir CIKARMA'dir, hicbir yerde yeni bir
# deger EKLENMESİ ornegi yoktur).
ExperienceLevel = Literal[
    "Internship",
    "New Graduate",
    "Entry Level",
    "Graduate Program",
    "Management Trainee",
    "MT Program",
    "0-2 Years Experience",
    "Junior",
]

# `Field(min_length=1)` dogrudan bir list/dict alanina uygulandiginda yalnizca
# DIS kabin boyutunu kisitlar (orn. "en az 1 anahtar") - IC elemanlarin
# (orn. bos bir departman adi "" veya bos bir unvan listesi) kendisini
# kisitlamaz. `NonEmptyStr`/`NonEmptyStrList`, bu kisitlamayi eleman
# duzeyinde de zorunlu kilmak icin kullanilir (bkz. TargetCriteria).
NonEmptyStr = Annotated[str, Field(min_length=1)]
NonEmptyStrList = Annotated[list[NonEmptyStr], Field(min_length=1)]


class TargetCriteria(BaseModel):
    """PRD Section 15.1/17: Target Locations/Departments/Experience Levels
    + M1.4'un ekledigi workplace_types alani (bkz. default.account.yaml
    account_config_overrides)."""

    model_config = ConfigDict(extra="forbid")

    locations: NonEmptyStrList
    departments: Annotated[dict[NonEmptyStr, NonEmptyStrList], Field(min_length=1)]
    experience_levels: Annotated[list[ExperienceLevel], Field(min_length=1)]
    workplace_types: Annotated[list[WorkplaceType], Field(min_length=1)]


class AIMatchWeights(BaseModel):
    """PRD Section 13.1: AI Match Score bilesen agirliklari. Toplamin
    %100 olmasi gerekliligi tek-alan araligiyla ifade edilemeyen
    capraz-alan bir kuraldir - bkz. config/validator.py."""

    model_config = ConfigDict(extra="forbid")

    department_role_relevance: float = Field(ge=0, le=1)
    experience_level_fit: float = Field(ge=0, le=1)
    location_fit: float = Field(ge=0, le=1)
    company_quality_contribution: float = Field(ge=0, le=1)
    career_goal_alignment: float = Field(ge=0, le=1)


class CompanyQualityWeights(BaseModel):
    """PRD Section 12.1: Company Quality Score boyut agirliklari."""

    model_config = ConfigDict(extra="forbid")

    brand_reputation_prestige: float = Field(ge=0, le=1)
    company_scale: float = Field(ge=0, le=1)
    career_development_training_culture: float = Field(ge=0, le=1)
    sector_position: float = Field(ge=0, le=1)
    corporate_stability: float = Field(ge=0, le=1)
    external_signals: float = Field(ge=0, le=1)


class Thresholds(BaseModel):
    """PRD Section 17 esik tablosu + Section 12.4'un tazelik penceresi."""

    model_config = ConfigDict(extra="forbid")

    company_quality_score: float = Field(ge=0, le=100)
    ai_match_score: float = Field(ge=0, le=100)
    department_confidence: float = Field(ge=0, le=1)
    borderline_band_width: float = Field(ge=0)
    company_score_reevaluation_window_days: int = Field(gt=0)


class Schedule(BaseModel):
    """PRD Section 14/17: calisma sikligi + zamanlama sapmasi (jitter)."""

    model_config = ConfigDict(extra="forbid")

    interval_days: int = Field(gt=0)
    jitter_minutes: int = Field(ge=0)


class CollectionLimits(BaseModel):
    """FR-21: calistirma basina toplama hacmi ust siniri."""

    model_config = ConfigDict(extra="forbid")

    max_jobs_per_run: int = Field(gt=0)


class NotificationSettings(BaseModel):
    """PRD Section 17.1: V1'de aktif kanal yok; sema Phase 2 icin
    simdiden ayrilir."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    channels: list[NonEmptyStr]


class ReportFormatSettings(BaseModel):
    """PRD Section 16/17.1: rapor format/sablon/dil ayarlari."""

    model_config = ConfigDict(extra="forbid")

    format: str = Field(min_length=1)
    template: str = Field(min_length=1)
    top_matches_count: int = Field(gt=0)
    language: str = Field(min_length=1)


class PromptTemplateRefs(BaseModel):
    """TDD Section 5/10: dort prompt sablonuna referanslar (dosyalar
    M5.2'de olusturulacak; bu alan yalnizca referans degeri tasir)."""

    model_config = ConfigDict(extra="forbid")

    department_matching: str = Field(min_length=1)
    experience_inference: str = Field(min_length=1)
    company_scoring: str = Field(min_length=1)
    ai_match_rationale: str = Field(min_length=1)


class AccountConfigProfile(BaseModel):
    """TDD Section 15: account_config_profiles satirinin JSONB alanlarinin
    tam semasi."""

    model_config = ConfigDict(extra="forbid")

    target_criteria: TargetCriteria
    weights_ai_match: AIMatchWeights
    weights_company_quality: CompanyQualityWeights
    thresholds: Thresholds
    schedule: Schedule
    collection_limits: CollectionLimits
    notification_settings: NotificationSettings
    report_format_settings: ReportFormatSettings
    prompt_template_refs: PromptTemplateRefs
