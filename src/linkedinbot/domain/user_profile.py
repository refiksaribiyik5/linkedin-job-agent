"""User Profile - kullanici/hesap profili (PRD Section 15.1).

Bu bir Account-Scoped varliktir (PRD Section 15.0).

Target Departments / Target Locations / Target Experience Levels, PRD
15.1'in kendi "Not (versiyonlama)" metninde acikca belirtildigi ve TDD'nin
duzeltilmis semasinda uygulandigi uzere, User Profile'da degil, Section
17'deki diger parametrelerle ayni versiyonlanmis konfigurasyon profilinde
(henuz M1.1'de tanimli olmayan AccountConfigProfile - bkz. M2.1) saklanir.
Bu yuzden bu modulde yer almazlar.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Preferences(BaseModel):
    """FR-19: kullanici belirli bir sirketi veya belirli bir ilani kod
    degisikligi gerektirmeden dislayabilir. PRD 15.1'deki "Preferences /
    Dealbreakers" alaninin acikca gerekcelendirilen tek somut icerigi budur;
    baska bir tercih turu herhangi bir PRD/TDD bolumunde adlandirilmadigi
    icin burada icerilmez.
    """

    excluded_companies: list[str] = Field(default_factory=list)
    excluded_job_ids: list[str] = Field(default_factory=list)


class UserProfile(BaseModel):
    """PRD Section 15.1 - User Profile (Target Departments/Locations/
    Experience Levels haric - yukaridaki modul dokumanina bakiniz).
    """

    career_goals: str
    skills_summary: str
    preferences: Preferences = Field(default_factory=Preferences)
