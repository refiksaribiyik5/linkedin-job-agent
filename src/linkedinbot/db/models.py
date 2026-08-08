"""SQLAlchemy 2.0 ORM modelleri - TDD Section 15 (v1.1 duzeltmeleri dahil).

Bu modul, PRD Section 15 ve TDD Section 15'teki 11 tabloyu (5 mimari
duzeltme dahil: accounts.next_run_at, account_config_profiles.target_criteria,
company_scores.rubric_version, job_postings.content_hash kapsami, ve
run_locks.lock_expires_at) SQLAlchemy 2.x'in tipli deklaratif stiliyle
(Mapped[]/mapped_column()) somutlastirir.

Adlandirma: ORM siniflari, M1.1'in Pydantic domain modelleriyle (ayni
kavramsal varligi temsil eden ama farkli bir katmana ait) isim
carpismasini onlemek icin "Orm" son eki tasir (orn. EvaluatedJobOrm vs.
domain.evaluated_job.EvaluatedJob). Bu, TDD Section 3'un "Adapters -> ...
-> Domain" bagimlilik yonu geregi izin verilen bir ice aktarimdir: bu
modul, ENUM sutunlari icin M1.1'de zaten tanimlanmis Python enum'larini
(JobStatus, WorkplaceType, TriggerType, RunStatus) yeniden kullanir --
ayni kavramin iki farkli yerde tanimlanip zamanla birbirinden sapmasini
onler.

Bu modulde COZULEN iki mimari bosluk (TDD'nin kompakt tablo notasyonunun
acikca belirtmedigi ama zorunlu kilan noktalar):

1. `company_scores` composite PK'si (`company_id`, `weight_profile_id`,
   `rubric_version`) nullable bir `weight_profile_id` icerir - PostgreSQL
   NULL degeri bir PK sutununda ASLA kabul etmez (bu bir stil tercihi
   degil, sabit bir kisittir). Kullanicinin onayladigi cozum: surrogate
   `id` (UUID) PK + iki kismi (partial) unique index -- biri
   weight_profile_id IS NULL icin (sistem varsayilani, sirket+rubric
   basina en fazla bir paylasilan skor), digeri weight_profile_id IS NOT
   NULL icin (hesaba ozel agirlik, sirket+profil+rubric basina en fazla
   bir skor). TDD'nin tam olarak amacladigi semantigi (NULL = paylasilan
   varsayilan) hicbir yeni anlam icat etmeden korur.

2. `reports` <-> `run_logs` (1)->(1) iliskisi (TDD Section 16, v1.1
   duzeltmesi) hicbir tabloda somut bir sutun olarak listelenmemisti.
   Dogal yon (bir Run tam olarak bir Report uretir) geregi `reports`
   tablosuna `run_id` (FK -> run_logs.run_id, UNIQUE) eklendi.

Ayrica: `evaluated_jobs.status`, TDD Section 15'in bu tablodaki metninde
hala eski (6 degerli, Borderline dahil) ENUM'u listeler; ancak TDD
Section 17 ("Durum Yonetimi") Borderline'in ayri bir boolean bayrak
(is_borderline) olmasi gerektigini acikca belirtir ve M1.1'de bu ikinci,
daha ayrintili cozum onaylanarak uygulanmisti (JobStatus: 5 deger +
is_borderline sutunu). Bu modul, domain/DB tutarliligi icin ayni cozumu
kullanir.

M1.2 sonrasi uretim-oncesi incelemede bulunan ve burada duzeltilen
konular:

- ENUM sutunlari (job_status, run_status, trigger_type, session_status,
  workplace_type), M1.1'in Python enum'larini dogrudan `sa.Enum(...)`'a
  vermenin SQLAlchemy'nin VARSAYILAN davranisi geregi, enum uyesinin
  `.value`'su degil `.name`'i (orn. "Hybrid" degil "HYBRID") PostgreSQL
  native ENUM etiketi olarak sakladigini ortaya cikardi -- bu, gercek
  bir veriyle dogrulanmis hataydi (bkz. testler), sadece bir stil
  meselesi degil. `values_callable` ile acikca `.value` kullanilarak
  duzeltildi.
- `account_config_profiles.is_active` icin TDD Section 16'nin acikca
  belirttigi "tam olarak bir tanesi is_active=true" kuralini zorunlu
  kilan kismi (partial) unique index eklendi.
- `ai_match_score`, `score_total` ve is_borderline-benzeri sayisal
  alanlar icin, M1.1'in Pydantic dogrulamasinin (0-100, >=0) DB
  katmaninda hicbir karsiligi olmadigi (savunma derinligi eksikligi)
  tespit edildi; CHECK kisitlari ve uygun precision/scale eklendi.
- Surrogate UUID PK'lere `server_default=gen_random_uuid()` eklendi;
  boylece ORM disi (raw SQL / gelecekteki baska bir servis) ekleme
  yollari da hata vermeden calisabilir (ORM yolu, mevcut Python-tarafi
  `default=uuid.uuid4` davranisini degistirmeden kullanmaya devam eder).

BILINCLI OLARAK DUZELTILMEYEN (M1.3'e birakilan) bir mimari risk:
ENUM sutunlarinin M1.1'in domain enum siniflarini DOGRUDAN kullanmasi
(asagida), bu dosyayi domain katmanina TDD Section 3'un izin verdigi
yonde (Adapters -> Domain) baglar, ancak bunun bir sonucu olarak
domain enum'unda saf is-mantigi nedeniyle yapilacak bir degisiklik
sessizce bir DB migration'i gerektirir hale gelir. Bu coupling'i tam
olarak cozmek (domain <-> DB donusumunu acik bir eslesme katmaninda
yapmak), tam olarak M1.3'un (Repository katmani) sorumluluk alanidir;
burada onceden bir soyutlama katmani insa etmek kapsam disina
tasmaktir. Enum degerlerinin artik dogru saklanmasi (yukaridaki
values_callable duzeltmesi) bu riski azaltir ama ortadan kaldirmaz --
M1.3, repository'leri yazarken bu coupling'i bilerek ele almalidir.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from linkedinbot.domain.evaluated_job import JobStatus
from linkedinbot.domain.job_posting import WorkplaceType
from linkedinbot.domain.run_log import RunStatus, TriggerType


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """`sa.Enum(...)` varsayilan olarak `.name`'i (orn. "HYBRID") native
    Postgres ENUM etiketi olarak kullanir; PRD/domain'in belirttigi
    `.value`'yu (orn. "Hybrid") DEGIL. Bu, gercek bir veritabanina
    yazilip okunarak dogrulanmis bir hataydi (bkz. modul dokumani).
    `values_callable=_enum_values` bunu acikca `.value` kullanmaya
    zorlar.
    """
    return [member.value for member in enum_cls]


class Base(DeclarativeBase):
    pass


class SessionStatus(enum.StrEnum):
    """TDD Section 15: linkedin_sessions.session_status (ENUM: valid/expired/unknown).

    Domain katmaninda karsiligi yoktur: LinkedInSession, henuz var olmayan
    adapters/linkedin katmaninin (M3.1) ilgi alanidir; bu yuzden burada,
    yalnizca DB semasi icin tanimlanir.
    """

    VALID = "valid"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Account-Scoped tablolar (PRD Section 15.0)
# ---------------------------------------------------------------------------


class AccountOrm(Base):
    """TDD Section 15: accounts (+ next_run_at, v1.1 duzeltmesi)."""

    __tablename__ = "accounts"

    account_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    display_name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # TDD, "status" alaninin olasi degerlerini hicbir yerde tanimlamaz;
    # bu yuzden kapali bir enum icat etmek yerine duz metin olarak birakilir.
    status: Mapped[str] = mapped_column(String)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserProfileOrm(Base):
    """TDD Section 15: user_profiles (Target Departments/Locations/Experience
    Levels haric - bkz. PRD Section 15.1 versiyonlama notu, M1.1).
    """

    __tablename__ = "user_profiles"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.account_id"), primary_key=True
    )
    career_goals: Mapped[str] = mapped_column(Text)
    skills_summary: Mapped[str] = mapped_column(Text)
    preferences_dealbreakers: Mapped[dict] = mapped_column(JSONB, default=dict)


class AccountConfigProfileOrm(Base):
    """TDD Section 15: account_config_profiles (+ target_criteria, v1.1
    duzeltmesi). Composite PK (account_id, config_version).

    TDD Section 16 ER diyagrami acikca "tam olarak bir tanesi
    is_active=true" der; bu, __table_args__'taki kismi unique index ile
    zorunlu kilinir (yalnizca hesap basina en fazla bir aktif profil).
    """

    __tablename__ = "account_config_profiles"
    __table_args__ = (
        Index(
            "uq_account_config_profiles_one_active",
            "account_id",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.account_id"), primary_key=True
    )
    config_version: Mapped[int] = mapped_column(Integer, primary_key=True)

    target_criteria: Mapped[dict] = mapped_column(JSONB)
    weights_ai_match: Mapped[dict] = mapped_column(JSONB)
    weights_company_quality: Mapped[dict] = mapped_column(JSONB)
    thresholds: Mapped[dict] = mapped_column(JSONB)
    schedule: Mapped[dict] = mapped_column(JSONB)
    collection_limits: Mapped[dict] = mapped_column(JSONB)
    notification_settings: Mapped[dict] = mapped_column(JSONB)
    report_format_settings: Mapped[dict] = mapped_column(JSONB)
    prompt_template_refs: Mapped[dict] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LinkedInSessionOrm(Base):
    """TDD Section 15: linkedin_sessions (FR-1)."""

    __tablename__ = "linkedin_sessions"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.account_id"), primary_key=True
    )
    # Hesap olusturulup ilk girisin yapilmasi arasinda henuz bir oturum
    # olmayabilecegi icin nullable (bkz. FR-1, M3.1'de doldurulur).
    encrypted_storage_state_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_status: Mapped[SessionStatus] = mapped_column(
        SqlEnum(SessionStatus, name="session_status", values_callable=_enum_values)
    )
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EvaluatedJobOrm(Base):
    """TDD Section 15: evaluated_jobs (PRD 15.4). status/is_borderline icin
    bkz. modul dokumanindaki not (Section 15 vs. Section 17 celiskisi,
    M1.1'de onaylanan cozum).
    """

    __tablename__ = "evaluated_jobs"
    __table_args__ = (
        UniqueConstraint("account_id", "job_id", name="uq_evaluated_jobs_account_job"),
        ForeignKeyConstraint(
            ["account_id", "config_version_used"],
            ["account_config_profiles.account_id", "account_config_profiles.config_version"],
            name="fk_evaluated_jobs_config_version",
        ),
        Index("ix_evaluated_jobs_account_status", "account_id", "status"),
        Index("ix_evaluated_jobs_job_account", "job_id", "account_id"),
        # FR-7 / Section 13: AI Match Score 0-100 araliginda tanimlidir.
        # M1.1'in Pydantic dogrulamasinin (ge=0, le=100) DB katmanindaki
        # savunma-derinligi karsiligi.
        CheckConstraint(
            "ai_match_score IS NULL OR (ai_match_score >= 0 AND ai_match_score <= 100)",
            name="ck_evaluated_jobs_ai_match_score_range",
        ),
        CheckConstraint(
            "report_appearances_count >= 0",
            name="ck_evaluated_jobs_report_appearances_count_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.account_id"))
    job_id: Mapped[str] = mapped_column(ForeignKey("job_postings.job_id"))
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.company_id"))

    # Numeric(5, 2): 0.00-100.00 araligini rahatca kapsar (bkz. CHECK kisiti
    # asagida); ciplak Numeric() sinirsiz hassasiyet/olcek anlamina gelirdi.
    ai_match_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    match_rationale: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Section 11.4 filtre sirasi geregi (Location -> Experience -> Department),
    # Department filtresine hic ulasamayan (daha once elenen) bir ilan bu
    # alani hicbir zaman almaz; bu yuzden nullable.
    department_cluster: Mapped[str | None] = mapped_column(Text, nullable=True)
    filter_result_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[JobStatus] = mapped_column(
        SqlEnum(JobStatus, name="job_status", values_callable=_enum_values)
    )
    is_borderline: Mapped[bool] = mapped_column(Boolean, default=False)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_appearances_count: Mapped[int] = mapped_column(Integer, default=0)

    content_hash_at_evaluation: Mapped[str] = mapped_column(Text)
    # account_id ile birlikte account_config_profiles'in composite PK'sine
    # (account_id, config_version) referans veren bilesik FK'nin ikinci yarisi.
    config_version_used: Mapped[int] = mapped_column(Integer)


class ReportOrm(Base):
    """TDD Section 15: reports (PRD 15.5).

    run_id: TDD Section 16'nin (v1.1) run_logs (1)->(1) reports iliskisini
    somutlastirir (bkz. modul dokumani, "cozulen bosluk #2").
    """

    __tablename__ = "reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "config_snapshot_ref"],
            ["account_config_profiles.account_id", "account_config_profiles.config_version"],
            name="fk_reports_config_snapshot",
        ),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.account_id"))
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("run_logs.run_id"), unique=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    included_job_ids: Mapped[list] = mapped_column(JSONB, default=list)
    top_matches: Mapped[list] = mapped_column(JSONB, default=list)

    format: Mapped[str] = mapped_column(String, default="Markdown")
    # config_version'a esittir; account_id ile birlikte account_config_profiles'in
    # composite PK'sine referans veren bilesik FK'nin ikinci yarisi.
    config_snapshot_ref: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(Text)


class RunLogOrm(Base):
    """TDD Section 15: run_logs (+ collection_capped, PRD 15.6 / FR-21).

    ended_at, M1.1'in Pydantic domain modelinde genel kavram geregi
    Optional'dir; burada NOT NULL'dur, cunku TDD Section 17'nin atomiklik
    stratejisi run_logs satirinin YALNIZCA calistirma sonlandiktan sonra,
    tek bir atomik transaction icinde yazildigini acikca belirtir - satir
    var oldugunda ended_at zaten bilinir.
    """

    __tablename__ = "run_logs"
    __table_args__ = (
        Index("ix_run_logs_account_started", "account_id", "started_at"),
        # M1.1'in Pydantic dogrulamasinin (ge=0) DB katmanindaki karsiligi.
        CheckConstraint("jobs_collected >= 0", name="ck_run_logs_jobs_collected_non_negative"),
        CheckConstraint("jobs_filtered >= 0", name="ck_run_logs_jobs_filtered_non_negative"),
        CheckConstraint("jobs_new >= 0", name="ck_run_logs_jobs_new_non_negative"),
        CheckConstraint("jobs_closed >= 0", name="ck_run_logs_jobs_closed_non_negative"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.account_id"))
    trigger_type: Mapped[TriggerType] = mapped_column(
        SqlEnum(TriggerType, name="trigger_type", values_callable=_enum_values)
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    jobs_collected: Mapped[int] = mapped_column(Integer, default=0)
    jobs_filtered: Mapped[int] = mapped_column(Integer, default=0)
    jobs_new: Mapped[int] = mapped_column(Integer, default=0)
    jobs_closed: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[RunStatus] = mapped_column(
        SqlEnum(RunStatus, name="run_status", values_callable=_enum_values)
    )
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    collection_capped: Mapped[bool] = mapped_column(Boolean, default=False)


class RunLockOrm(Base):
    """TDD Section 15: run_locks (+ lock_expires_at, v1.1 duzeltmesi,
    Section 14 cakisma onleme).
    """

    __tablename__ = "run_locks"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.account_id"), primary_key=True
    )
    # Hesap kilitli degilken (normal durum) her uc alan da NULL'dur.
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_owner: Mapped[str | None] = mapped_column(String, nullable=True)
    lock_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ---------------------------------------------------------------------------
# Shared/Reference tablolar (PRD Section 15.0)
# ---------------------------------------------------------------------------


class CompanyOrm(Base):
    """TDD Section 15: companies (PRD 15.3, yalnizca referans alanlari)."""

    __tablename__ = "companies"

    company_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    # Section 12.3: sirket hakkinda yeterli veri bulunamayabilir ("Unrated").
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    employee_count_range: Mapped[str | None] = mapped_column(String, nullable=True)
    founded_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CompanyScoreOrm(Base):
    """TDD Section 15: company_scores (+ rubric_version, v1.1 duzeltmesi).

    PK yapisi icin bkz. modul dokumanindaki "cozulen bosluk #1" -- surrogate
    `id` PK + iki kismi unique index, TDD'nin NULL=sistem-varsayilani
    semantigini teknik olarak imkansiz bir composite PK olmadan korur.
    """

    __tablename__ = "company_scores"
    __table_args__ = (
        Index(
            "uq_company_scores_default",
            "company_id",
            "rubric_version",
            unique=True,
            postgresql_where=text("weight_profile_id IS NULL"),
        ),
        Index(
            "uq_company_scores_custom",
            "company_id",
            "weight_profile_id",
            "rubric_version",
            unique=True,
            postgresql_where=text("weight_profile_id IS NOT NULL"),
        ),
        Index("ix_company_scores_company_weight_profile", "company_id", "weight_profile_id"),
        # Section 12: Company Quality Score 0-100 araliginda tanimlidir.
        CheckConstraint(
            "score_total IS NULL OR (score_total >= 0 AND score_total <= 100)",
            name="ck_company_scores_score_total_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.company_id"))
    # NULL = sistem varsayilani (bkz. Section 12.4). TDD bu alani "(FK)"
    # olarak isaretlemez; bu yuzden burada da bicimsel bir FK kisiti yoktur.
    weight_profile_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    rubric_version: Mapped[int] = mapped_column(Integer)

    score_total: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    score_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class JobPostingOrm(Base):
    """TDD Section 15: job_postings (PRD 15.2, hesap tasimaz)."""

    __tablename__ = "job_postings"
    __table_args__ = (Index("ix_job_postings_content_hash", "content_hash"),)

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.company_id"))
    location_text: Mapped[str] = mapped_column(String)
    workplace_type: Mapped[WorkplaceType | None] = mapped_column(
        SqlEnum(WorkplaceType, name="workplace_type", values_callable=_enum_values), nullable=True
    )
    posted_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    description: Mapped[str] = mapped_column(Text)
    employment_type: Mapped[str | None] = mapped_column(String, nullable=True)
    easy_apply: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    application_url: Mapped[str] = mapped_column(Text)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Yalnizca Title/Experience Level/Location/Workplace Type/Description
    # alanlarindan hesaplanir (bkz. FR-14, M4.1).
    content_hash: Mapped[str] = mapped_column(Text)
