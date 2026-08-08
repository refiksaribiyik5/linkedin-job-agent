import pytest
from pydantic import ValidationError

from linkedinbot.domain.user_profile import Preferences, UserProfile


def test_valid_user_profile_with_default_preferences():
    profile = UserProfile(
        career_goals="Business Development alaninda kariyer",
        skills_summary="Satis, iletisim",
    )
    assert profile.preferences.excluded_companies == []
    assert profile.preferences.excluded_job_ids == []


def test_valid_user_profile_with_explicit_blacklist():
    # FR-19: kullanici belirli bir sirketi veya ilani dislayabilir.
    profile = UserProfile(
        career_goals="Business Development",
        skills_summary="Satis",
        preferences=Preferences(
            excluded_companies=["Kotu Sirket A.S."],
            excluded_job_ids=["linkedin-999"],
        ),
    )
    assert "Kotu Sirket A.S." in profile.preferences.excluded_companies
    assert "linkedin-999" in profile.preferences.excluded_job_ids


def test_missing_career_goals_raises_validation_error():
    with pytest.raises(ValidationError):
        UserProfile(skills_summary="Satis")


def test_missing_skills_summary_raises_validation_error():
    with pytest.raises(ValidationError):
        UserProfile(career_goals="Business Development")


def test_user_profile_has_no_target_criteria_fields():
    # PRD 15.1 "Not (versiyonlama)": Target Departments/Locations/Experience
    # Levels User Profile'da degil, AccountConfigProfile'da tutulur.
    field_names = set(UserProfile.model_fields)
    assert "target_departments" not in field_names
    assert "target_locations" not in field_names
    assert "target_experience_levels" not in field_names


def test_preferences_rejects_unrecognized_fields():
    # M1.4 review duzeltmesi: Preferences yalnizca blacklist alanlarini
    # tasir (bkz. modul dokumani); baska bir alan (orn. cli.py:seed()'in
    # account_config_overrides'a yazmasi gereken "remote_work"/"language"
    # yanlislikla buraya konursa) sessizce yutulmak yerine acikca
    # reddedilmelidir - aksi halde seed edilen veri sessizce eksik kalir.
    with pytest.raises(ValidationError):
        Preferences(excluded_companies=[], excluded_job_ids=[], remote_work="hybrid")
