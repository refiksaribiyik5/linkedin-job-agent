"""Account - hesabin kendisi (TDD Section 15: accounts tablosu).

PRD Section 15 bu varligi bir "kavramsal varlik" olarak listelemez (PRD'nin
6 varligi: User Profile, Job Posting, Company Profile, Evaluated Job,
Report, Run Log) - `accounts` tablosu tamamen TDD'nin Section 1 Karar 3
("Hesap-Parametrik Cekirdek") ve Section 14'un (Multi-User Hazir Mimari)
getirdigi bir alt yapi kavramidir. Bu yuzden M1.1, ayri bir `Account`
domain modeli tanimlamamisti - yalnizca zaten var olan bir hesabi temsil
eden `AccountContext` (account_id + user_profile) tanimlanmisti.

M1.3'te repository katmani icin bu bosluk ortaya cikti: `account_repository`
somut bir hesap SATIRINI (display_name, created_at, status, next_run_at -
TDD Section 15) olusturup okuyabilmelidir, ama bunu temsil edecek hicbir
domain modeli yoktu. Bu modul o boslugu doldurur; AccountContext'i
degistirmez (o hala "account_id + cozumlenmis user_profile" anlamina
gelir), yalnizca "henuz cozumlenmemis, ham bir hesap kaydi" icin ayri bir
tip saglar.

account_id, Report.report_id/RunLog.run_id'nin aksine bilincli olarak
`UUID | None = None` olarak tanimlanir: o iki alanin cagirani (orn.
Reporting Compiler) UUID'yi cagirmadan once kendisi uretir; account_id
icin boyle bir on-uretim akisi hicbir PRD/TDD bolumunde tanimli degildir -
bir hesap yalnizca DB satiri olusturulunca (M1.4 seed script'i araciligiyla)
var olur ve account_id'yi veritabani (`gen_random_uuid()`) veya repository
uretir. Domain kimligini "veritabani-only" olarak gizli tutmak yerine (API,
onbellekleme, event, denetim gibi gelecekteki kullanimlar icin) acikca
Optional bir alan olarak modellenir; repository, kalicilik sonrasi bu
alani doldurup nesneyi geri doner.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class Account(BaseModel):
    """TDD Section 15 - accounts (+ next_run_at, v1.1 duzeltmesi).

    `status` icin TDD hicbir yerde kapali bir deger kumesi tanimlamaz
    (bkz. db/models.py'deki ayni gerekce); bu yuzden burada da kapali bir
    enum icat edilmez, duz metin olarak birakilir.
    """

    account_id: UUID | None = None
    display_name: str
    created_at: datetime
    status: str
    next_run_at: datetime | None = None
