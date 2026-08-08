"""SessionManager - `linkedin_port`'un M3.1 kapsamli implementasyonu
(yalnizca login+kaydetme yolu - Roadmap M3.1).

TDD Section 9: "SessionManager - `linkedin_port`'un bir parcasi; Playwright'in
`storage_state` (cerezler + local storage) mekanizmasiyla kalici oturumu
yukler/dogrular." Bu sinif o tanimin M3.1'de teslim edilen kismini
karsilar: `ensure_session()`, verilen hesap icin DB'de (`linkedin_sessions`)
kalici bir oturum referansi yoksa `playwright_client.perform_interactive_login`'i
(constructor'dan enjekte edilen bir callable olarak) tetikler, sonucu
Secrets Provider'a yazar ve DB satirini gunceller/olusturur. Oturumun
hala GECERLI olup olmadigini (sunucu tarafinda suresi dolmus mu)
dogrulayan `validate()` yolu KASITLI OLARAK burada YOKTUR - bu Roadmap
M3.2'nin scope'udur.

DB semasinin kendi belgeledigi gibi (bkz. db/models.py
`LinkedInSessionOrm.encrypted_storage_state_ref`), bu tabloya yazilan
deger ham storage_state DEGIL, Secrets Provider'daki gercek degere
giden bir REFERANS (anahtar adi)dir - ham veri hicbir zaman DB'ye
yazilmaz, yalnizca sifreli secrets deposuna (bkz. adapters.secrets).

DI deseni, kod tabaninin geri kalaniyla tutarlidir (bkz. cli.seed(),
LocalKeyringSecretsProvider): `Session` ve `SecretsProviderPort`
constructor'dan enjekte edilir (kendi kendine olusturulmaz); `account_id`
ise (repository'lerin `create()` metodlariyla ayni desende) HER cagriya
parametre olarak verilir, constructor'a gomulmez - TDD Section 14'un
"account_id parametresi olmadan hicbir Account-Scoped sorgu calismaz"
ilkesiyle tutarli. Bu sinif kendi basina COMMIT ETMEZ - transaction
sinirini cagiran yonetir (ayni `seed()` konvansiyonu).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from linkedinbot.db.models import LinkedInSessionOrm, SessionStatus
from linkedinbot.ports.linkedin_port import LinkedInPort
from linkedinbot.ports.secrets_provider_port import SecretsProviderPort


class SessionManager(LinkedInPort):
    def __init__(
        self,
        session: Session,
        secrets_provider: SecretsProviderPort,
        playwright_login: Callable[[], dict[str, Any]],
    ) -> None:
        self._session = session
        self._secrets_provider = secrets_provider
        self._playwright_login = playwright_login

    def ensure_session(self, account_id: UUID) -> None:
        existing = self._session.get(LinkedInSessionOrm, account_id)
        if existing is not None and existing.encrypted_storage_state_ref is not None:
            return

        storage_state = self._playwright_login()
        secret_key = f"linkedin_storage_state:{account_id}"
        now = datetime.now(UTC)

        # SIRALAMA KASITLIDIR (bagimsiz incelemede bulunan Major bulgunun
        # duzeltmesi): DB yazimi (flush) Secrets Provider yazimindan ONCE
        # yapilir. Bu iki kalicilik mekanizmasi (SQL transaction'i ve
        # Secrets Provider'in kendi dosyasi) ortak bir transaction
        # PAYLASMAZ - biri digerini geri alamaz. Eger secret ONCE
        # yazilsaydi ve DB flush'i SONRA basarisiz olsaydı, kullanicinin
        # tamamladigi pahali bir interaktif giris (2FA/CAPTCHA dahil)
        # bosa gitmis olurdu: hicbir DB satirinin referans vermedigi
        # "yetim" bir secret diskte kalirdi. Bu sirayla, DB basarisizligi
        # secret yazimindan ONCE gerceklesir (hicbir yetim secret asla
        # olusmaz); DB basarili ama secret yazimi SONRADAN basarisiz
        # olursa da, cagiran (established `cli.seed()`/`_run_seed_command`
        # rollback konvansiyonuyla tutarli sekilde) transaction'i temiz
        # bicimde geri alabilir - hicbir tutarsiz ara durum kalmaz.
        if existing is not None:
            existing.encrypted_storage_state_ref = secret_key
            existing.session_status = SessionStatus.VALID
            existing.last_validated_at = now
        else:
            self._session.add(
                LinkedInSessionOrm(
                    account_id=account_id,
                    encrypted_storage_state_ref=secret_key,
                    session_status=SessionStatus.VALID,
                    last_validated_at=now,
                )
            )
        self._session.flush()

        self._secrets_provider.set(secret_key, json.dumps(storage_state))
