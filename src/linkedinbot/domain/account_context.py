"""AccountContext - hesap-parametrik cekirdegin merkezi soyutlamasi
(TDD Section 1 Karar 3, Section 14).

TDD, AccountContext'i uc farkli yerde farkli sekilde tanimlar: Section 1
Karar 3 ozetle "account_id + o hesabın çözümlenmiş konfigürasyon profili"
der, Section 14 acikca "account_id + çözümlenmiş AccountConfigProfile +
UserProfile" der, Section 8'deki veri akisi tablosu ise
"AccountContext.secrets_ref" adinda bir alana atifta bulunur.

M1.1, yalnizca su an gercekten var olan tipleri (account_id, user_profile)
icerecek sekilde onaylanmisti; config_profile alaninin "AccountConfigProfile
tipi tanimlandiginda (M2.1) bir sonraki milestone (M2.2) tarafindan
eklenecegi" acikca not edilmisti. Bu modul o notu yerine getirir:
`config_version` ve `config_profile` eklenir (bkz. Roadmap M2.2, TDD
Section 23). secrets_ref alani HALA eklenmez: bir secrets deposu
referansi altyapisal bir kavramdir ve domain modelinde tutulmasi, domain
katmaninin altyapidan tamamen bagimsiz kalmasi gerekliligini ihlal eder;
secrets erisimi her zaman SecretsProvider port'u (M2.3) uzerinden yapilir.

Mimari not - `domain` neden `config`'i import eder: TDD Section 3'un genel
kurali "domain yalnizca Port arayuzlerine bagimlidir" der ve verdigi
somut ornekler (Playwright, SQLAlchemy, Anthropic SDK) ALTYAPI/adapter
teknolojileridir. `linkedinbot.config.schema`, domain modelleriyle ayni
ruhta, sifir altyapi bagimliligi olan SAF bir Pydantic modulüdür (yalnizca
pydantic + baska bir domain enum'u import eder) - bu yuzden bu import,
kuralin KORUMAYA calistigi seyi (domain'in Playwright/SQLAlchemy/DB'ye
baglanmasi) ihlal etmez. Daha da onemlisi, TDD Section 1/14'un kendisi
AccountContext'i acikca "account_id + AccountConfigProfile + UserProfile"
olarak TANIMLAR - bu, genel kuralin degil, bu spesifik, adi konmus
nesnenin somut sekli icin acik bir gereksinimdir. `config/schema.py`'yi
`domain/`'e tasimak (tersi) M2.1'in zaten denetlenmis/onaylanmis dosya
yerlesimini degistirir; bu yuzden tercih edilmedi (bkz. config/schema.py
M2.1 audit notlari).

`config_version` alani hakkinda: TDD Section 14'un AccountContext
tanimi yalnizca "AccountConfigProfile" der, ayrica bir versiyon numarasi
adlandirmaz. Ancak Section 15.5/17'nin "Config Snapshot Reference"
gereksinimi (bir raporun HANGI config versiyonuyla uretildiginin
sonradan dogrulanabilmesi) ancak versiyon numarasi "donmus" context'in
BIR PARCASI olarak tasinirsa anlamli sekilde karsilanabilir - aksi halde
ileride (M8.2/8.3) bir rapor derleyicisi, DB'deki "o an aktif" versiyonu
TEKRAR sorgulamak zorunda kalirdi, bu da tam olarak "donmus snapshot"
tasarim kararinin onlemeye calistigi tutarsizlik riskini geri getirir.
Bu, yeni bir yapi icat etmek degil, zaten adi gecen "config_profile"
kavramini kendi dogal kimlik alaniyla (account_config_profiles'in
composite PK'sinin ikinci yarisi) tamamlamaktir.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from linkedinbot.config.schema import AccountConfigProfile
from linkedinbot.domain.user_profile import UserProfile


class AccountContext(BaseModel):
    """Bir calistirmanin hangi hesap icin, hangi profille ve hangi
    (donmus) konfigurasyonla yurutuldugunu tasiyan nesne (bkz. TDD
    Appendix B, Section 1 Karar 3, Section 14, Section 23).
    """

    account_id: UUID
    user_profile: UserProfile
    config_version: int = Field(ge=1)
    config_profile: AccountConfigProfile
