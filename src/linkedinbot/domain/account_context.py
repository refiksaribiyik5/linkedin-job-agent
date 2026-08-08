"""AccountContext - hesap-parametrik cekirdegin merkezi soyutlamasi
(TDD Section 1 Karar 3, Section 14).

TDD, AccountContext'i uc farkli yerde farkli sekilde tanimlar: Section 1
ozetle "account_id + config profili" der, Section 14 "account_id +
AccountConfigProfile + UserProfile" der, Section 8'deki veri akisi
tablosu ise "AccountContext.secrets_ref" adinda bir alana atifta bulunur.

Bu modul, M1.1 icin acikca onaylanan cozume gore yalnizca su an gercekten
var olan tipleri icerir: account_id ve user_profile. config_profile alani,
AccountConfigProfile tipi tanimlandiginda (bkz. M2.1 config/schema.py) bu
modul uzerinde bir sonraki milestone tarafindan eklenecektir - bu, normal
artimli tipleme sureci olup mimariyi degistirmez. secrets_ref alani ise
hic eklenmez: bir secrets deposu referansi altyapisal bir kavramdir ve
domain modelinde tutulmasi, domain katmaninin altyapidan tamamen bagimsiz
kalmasi gerekliligini (bkz. TDD Section 3 "Bagimlilik yonu") ihlal eder;
secrets erisimi her zaman SecretsProvider port'u uzerinden yapilir.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from linkedinbot.domain.user_profile import UserProfile


class AccountContext(BaseModel):
    """Bir calistirmanin hangi hesap icin, hangi profille yurutuldugunu
    tasiyan nesne (bkz. TDD Appendix B).
    """

    account_id: UUID
    user_profile: UserProfile
