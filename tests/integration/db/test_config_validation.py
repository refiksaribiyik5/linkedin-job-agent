"""config/validator.py'nin gercek, kalici M1.4 seed verisiyle uyumlulugu
icin entegrasyon testi (Roadmap M2.1).

M2.1'in schema.py/validator.py'si M1.4'un GERCEKTEN urettigi sekli
modellemek uzere tasarlandi (bkz. her iki modulun de dokumani); bu test
bunu iddia olarak birakmaz, gercek Postgres konteynerindeki gercek
seed edilmis satiriyla dogrudan kanitlar.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from linkedinbot.config.validator import validate_config
from linkedinbot.db.models import AccountConfigProfileOrm


def test_real_seeded_config_profile_passes_m2_1_validation(db_session: Session):
    orm_profile = (
        db_session.execute(
            select(AccountConfigProfileOrm).where(AccountConfigProfileOrm.is_active.is_(True))
        )
        .scalars()
        .first()
    )
    assert orm_profile is not None, "Bu test M1.4'un seed'i calistirilmis bir DB'ye ihtiyac duyar"

    data = {
        "target_criteria": orm_profile.target_criteria,
        "weights_ai_match": orm_profile.weights_ai_match,
        "weights_company_quality": orm_profile.weights_company_quality,
        "thresholds": orm_profile.thresholds,
        "schedule": orm_profile.schedule,
        "collection_limits": orm_profile.collection_limits,
        "notification_settings": orm_profile.notification_settings,
        "report_format_settings": orm_profile.report_format_settings,
        "prompt_template_refs": orm_profile.prompt_template_refs,
    }

    validated = validate_config(data)

    assert validated.thresholds.ai_match_score == 60
    assert validated.thresholds.company_quality_score == 50
    assert validated.target_criteria.locations == ["Istanbul"]
