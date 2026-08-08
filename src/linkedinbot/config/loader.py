"""Config Loader - hesap-basina "donmus" AccountContext uretimi (Roadmap
M2.2, TDD Section 23).

Bu modul, TDD Section 1 Karar 3 / Section 14'un tanimladigi AccountContext'i
("hesap kimligi + o hesabin cozumlenmis konfigurasyon profili") somutlastirir:
verilen bir `account_id` icin `accounts`/`user_profiles`/`account_config_profiles`
satirlarini okur, `account_config_profiles`'in JSONB icerigini M2.1'in
`validate_config()`'u ile DOGRULAR (TDD Section 23(b): "Calistirma
baslangicinda - savunma amacli ikinci bir dogrulama... fail-fast" - M2.4'un
yazma-zamani dogrulama komutu henuz yazilmadigi icin bu, sistemdeki TEK
fiilen calisan dogrulama noktasidir), ve hepsini tek, tutarli bir
AccountContext nesnesinde birlestirir.

Bu modul, `config/system.defaults.yaml` veya `config/accounts/*.yaml`
dosyalarina HIC DOKUNMAZ. TDD Section 23'un 4 katmanli oncelik zinciri
(kod-ici varsayilan -> system.defaults.yaml -> hesap profili -> env), bir
`account_config_profiles` SATIRININ NASIL URETILDIGINI (M1.4'un `seed()`'i
gibi bir yazma-zamani akisinda system defaults + hesaba-ozel override'lari
BIR KEZ birlestirip DB'ye yazarak) tarif eder; bir satir bir kez
yazildiktan sonra ZATEN tam cozumlenmis durumdadir. Bu yuzden bu loader'in
isi zincirin 1-3. katmanlarini HER YUKLEMEDE tekrar tekrar cozmek degil,
zaten cozumlenmis SONUCU (DB satirini) okuyup dogrulamaktir. 4. katman
(ortam degiskenleri) hicbir zaman is konfigurasyonunu etkilemez (TDD
Section 23: "is kurali asla env var ile gecersiz kilinmaz") - bu yuzden
burada da hic yer almaz.

"Donmus" (frozen) snapshot: `load_account_context()`'in dondugu
`AccountContext` nesnesi, DB'den okunan verilerden BIR KEZ olusturulan
duz bir Python nesnesidir - DB'ye canli bir baglanti tasimaz, sonraki bir
DB degisikliginden otomatik olarak etkilenmez. Bu, TDD Section 23'un
"config... AccountContext icine 'dondurulur'... calistirma boyunca
tutarli bir gorunum kullanilir" gereksinimini normal Python nesne
semantigiyle dogal olarak karsilar; ek bir mekanizma gerekmez.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from linkedinbot.config.validator import validate_config
from linkedinbot.db.models import AccountConfigProfileOrm
from linkedinbot.db.repositories.account_repository import SqlAlchemyAccountRepository
from linkedinbot.db.repositories.user_profile_repository import SqlAlchemyUserProfileRepository
from linkedinbot.domain.account_context import AccountContext


def load_account_context(account_id: UUID, session: Session) -> AccountContext:
    """Roadmap M2.2 "Beklenen Sonuc": dogrulanmis, versiyonlanmis, tam
    cozumlenmis bir konfigurasyonu (bir `AccountContext` icinde) doner.

    Sirayla, her biri acikca basarisiz olabilen (fail-fast, hicbir zaman
    sessiz bir varsayilana dusmeyen - FR-13/EDGE-15):

    1. Hesabin var oldugu dogrulanir (`AccountRepositoryPort`).
    2. `UserProfile` okunur (`UserProfileRepositoryPort`).
    3. Hesabin aktif (`is_active=true`) `account_config_profiles` satiri
       okunur.
    4. O satirin JSONB icerigi M2.1'in `validate_config()`'u ile
       dogrulanir (TDD Section 23(b) savunma-amacli ikinci dogrulama).
    5. Hepsi tek bir `AccountContext`'te birlestirilir.

    Hicbir adim bulunamama/gecersizlik durumunda sessizce bir varsayilana
    veya bos degere DUSMEZ - acik bir `ValueError` (M1.3 repository'lerinin
    "bulunamadi" hatalarinda kullandigi ayni desen) veya M2.1'in
    `ConfigValidationError`'i firlatilir.
    """
    account_repo = SqlAlchemyAccountRepository(session)
    if account_repo.get_by_id(account_id) is None:
        raise ValueError(f"Hesap bulunamadi: {account_id}")

    user_profile_repo = SqlAlchemyUserProfileRepository(session)
    user_profile = user_profile_repo.get_by_account_id(account_id)
    if user_profile is None:
        raise ValueError(f"Bu hesap icin kullanici profili bulunamadi: {account_id}")

    orm_config_profile = (
        session.execute(
            select(AccountConfigProfileOrm).where(
                AccountConfigProfileOrm.account_id == account_id,
                AccountConfigProfileOrm.is_active.is_(True),
            )
        )
        .scalars()
        .first()
    )
    if orm_config_profile is None:
        raise ValueError(f"Bu hesap icin aktif bir config profili bulunamadi: {account_id}")

    config_profile = validate_config(
        {
            "target_criteria": orm_config_profile.target_criteria,
            "weights_ai_match": orm_config_profile.weights_ai_match,
            "weights_company_quality": orm_config_profile.weights_company_quality,
            "thresholds": orm_config_profile.thresholds,
            "schedule": orm_config_profile.schedule,
            "collection_limits": orm_config_profile.collection_limits,
            "notification_settings": orm_config_profile.notification_settings,
            "report_format_settings": orm_config_profile.report_format_settings,
            "prompt_template_refs": orm_config_profile.prompt_template_refs,
        }
    )

    return AccountContext(
        account_id=account_id,
        user_profile=user_profile,
        config_version=orm_config_profile.config_version,
        config_profile=config_profile,
    )
