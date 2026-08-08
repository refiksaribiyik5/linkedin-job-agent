"""Config dogrulama katmani (Roadmap M2.1, FR-13/EDGE-15).

`config/schema.py`'nin Pydantic modelleri sekil duzeyindeki dogrulamayi
(tip, tek-alan araligi, taninmayan anahtar) zaten yapar (bkz. schema.py
modul dokumani). Bu modul, tek bir alanin kendi `Field(ge=, le=)` siniriyla
ifade edilemeyen CAPRAZ-ALAN / is-kurali duzeyindeki kontrolleri (agirlik
toplaminin %100 olmasi) ekler ve butun ihlalleri TEK BIR anlasilir hata
mesajinda toplar (Roadmap M2.1 "Beklenen Sonuc": "...anlasilir bir hata
mesaji uretir" - yalnizca ilk hatada durup gerisini gizlemek bu
gereksinimi karsilamaz).

TODO (KASITLI OLARAK BURAKILMIS, bkz. schema.py modul dokumani):
Roadmap M2.1'in "tanimsiz bir departman referansi" ornegi burada
uygulanmamistir. M1.4'un target_criteria.departments alani bir referans
degil dogrudan bir taksonomi tanimidir (PRD Section 17'nin kendisi bunu
acik-uclu/genisletilebilir olarak tanimlar); bu kontrolu eklemek M1.4'un
onaylanmis veri modelini yeniden yapilandirmayi veya gereksinimi baska
bir alana uygulanacak sekilde yeniden yorumlamayi gerektirirdi - proje
talimati acikca ikisini de yasakladi. Bu bosluk, department_taxonomy'nin
mimariye eklendigi (orn. multi-user/SaaS fazinda birden fazla hesabin
departman secimlerini farklilastirmasi gerektiginde) bir gelecek
milestone'da yeniden degerlendirilmelidir.
"""

from __future__ import annotations

import math

from pydantic import ValidationError

from linkedinbot.config.schema import AccountConfigProfile

_WEIGHT_SUM_TOLERANCE = 1e-6
_EXPECTED_WEIGHT_SUM = 1.0


class ConfigValidationError(ValueError):
    """Bir veya daha fazla config kuralinin ihlal edildigini, TUMUNU tek
    bir anlasilir mesajda toplayarak bildirir (FR-13/Roadmap M2.1
    "anlasilir bir hata mesaji").
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Konfigurasyon gecersiz:\n" + "\n".join(f"- {e}" for e in errors))


def _weight_sum_error(weights: dict[str, float], label: str) -> str | None:
    total = sum(weights.values())
    if not math.isclose(total, _EXPECTED_WEIGHT_SUM, abs_tol=_WEIGHT_SUM_TOLERANCE):
        return f"{label} toplami %100 (1.0) olmalidir, ama {total} bulundu."
    return None


def validate_config(data: dict) -> AccountConfigProfile:
    """Ham bir dict'i (orn. DB'den okunan JSONB alanlarinin birlesimi)
    dogrular.

    Basarili olursa dogrulanmis `AccountConfigProfile` nesnesini doner;
    basarisiz olursa TUM ihlalleri (yalnizca ilki degil) tek bir
    `ConfigValidationError` icinde toplar.

    Iki asamali calisir: once schema.py'nin Pydantic modelleri TUM
    sekil-duzeyi ihlallerini (eksik/fazla alan, tip hatasi, tek-alan
    araligi disi deger) toplu halde raporlar; yalnizca sekil gecerliyse
    capraz-alan is kurallari (agirlik toplami) kontrol edilir - agirlik
    toplami, alanlarin turleri/varligi zaten dogrulanmadan anlamli
    sekilde hesaplanamaz.
    """
    try:
        profile = AccountConfigProfile.model_validate(data)
    except ValidationError as exc:
        raise ConfigValidationError(
            [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()]
        ) from exc

    errors = [
        error
        for error in (
            _weight_sum_error(
                profile.weights_ai_match.model_dump(), "AI Match Score bilesen agirliklari"
            ),
            _weight_sum_error(
                profile.weights_company_quality.model_dump(),
                "Company Quality Score boyut agirliklari",
            ),
        )
        if error is not None
    ]

    if errors:
        raise ConfigValidationError(errors)

    return profile
