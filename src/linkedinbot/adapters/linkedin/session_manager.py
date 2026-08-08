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
        self._secrets_provider.set(secret_key, json.dumps(storage_state))
        now = datetime.now(UTC)

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
