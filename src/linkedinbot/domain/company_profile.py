"""Company Profile - sirket referans verisi (PRD Section 15.3).

Bu bir Shared/Reference varligidir (PRD Section 15.0). Company Quality
Score ve Score Breakdown, PRD 15.3'te kavramsal olarak Company Profile'a
ait gorunse de, TDD'nin duzeltilmis mimarisinde (Section 12.4 coklu-kullanici
onbellekleme kurali) ayri bir company_scores kaydi olarak, Weight Profile ve
Rubric Version'a bagli sekilde tutulur. Bu modul yalnizca sirketin referans
verisini temsil eder; skorlama M7.1'de ayrica ele alinacaktir.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CompanyProfile(BaseModel):
    """PRD Section 15.3 - Company Profile (yalnizca referans alanlari).

    Section 12.3, sirket hakkinda yeterli veri bulunamayabilecegini
    ("Unrated" senaryosu) acikca kabul eder; bu yuzden kimlik disindaki
    alanlar opsiyoneldir.
    """

    company_id: str
    name: str

    industry: str | None = None
    employee_count_range: str | None = None
    founded_year: int | None = None
    last_evaluated_timestamp: datetime | None = None
