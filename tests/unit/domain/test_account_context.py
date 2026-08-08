from uuid import uuid4

import pytest
from pydantic import ValidationError

from linkedinbot.domain.account_context import AccountContext
from linkedinbot.domain.user_profile import UserProfile


def _user_profile():
    return UserProfile(career_goals="Business Development", skills_summary="Satis")


def test_valid_account_context():
    context = AccountContext(account_id=uuid4(), user_profile=_user_profile())
    assert isinstance(context.user_profile, UserProfile)


def test_missing_user_profile_raises_validation_error():
    with pytest.raises(ValidationError):
        AccountContext(account_id=uuid4())


def test_missing_account_id_raises_validation_error():
    with pytest.raises(ValidationError):
        AccountContext(user_profile=_user_profile())


def test_account_context_has_no_config_profile_or_secrets_field_yet():
    # TDD Section 1/8/14 AccountContext'i farkli sekillerde tanimlar; M1.1
    # icin onaylanan cozum: config_profile (AccountConfigProfile M2.1'de
    # tanimlanana kadar) ve secrets_ref (altyapisal, domain'e ait degil)
    # bu asamada eklenmez.
    field_names = set(AccountContext.model_fields)
    assert field_names == {"account_id", "user_profile"}
