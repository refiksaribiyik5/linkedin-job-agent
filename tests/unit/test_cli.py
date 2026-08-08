from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from linkedinbot import cli
from linkedinbot.cli import _deep_merge
from linkedinbot.domain.account import Account

NOW = datetime(2026, 8, 8, tzinfo=UTC)


def test_deep_merge_overrides_leaf_value():
    base = {"a": 1, "b": 2}
    overrides = {"b": 20}

    assert _deep_merge(base, overrides) == {"a": 1, "b": 20}


def test_deep_merge_recurses_into_nested_dicts_preserving_sibling_keys():
    # M1.4 seed script'inin tam olarak dayandigi davranis: target_criteria
    # icindeki "locations" ezilirken "departments"/"experience_levels"
    # sistem varsayilanindan korunmalidir.
    base = {
        "target_criteria": {
            "locations": ["Istanbul"],
            "departments": {"Sales": ["Sales Executive"]},
            "experience_levels": ["Entry Level"],
        }
    }
    overrides = {
        "target_criteria": {
            "locations": ["Istanbul"],
            "workplace_types": ["On-site", "Hybrid"],
        }
    }

    merged = _deep_merge(base, overrides)

    assert merged["target_criteria"]["locations"] == ["Istanbul"]
    assert merged["target_criteria"]["workplace_types"] == ["On-site", "Hybrid"]
    assert merged["target_criteria"]["departments"] == {"Sales": ["Sales Executive"]}
    assert merged["target_criteria"]["experience_levels"] == ["Entry Level"]


def test_deep_merge_does_not_mutate_base():
    base = {"a": {"x": 1}}
    overrides = {"a": {"y": 2}}

    _deep_merge(base, overrides)

    assert base == {"a": {"x": 1}}


def test_deep_merge_non_dict_override_replaces_dict_wholesale():
    # Bir taraf dict, diger taraf degilse recursive birlestirme yapilmaz -
    # overrides'taki deger oldugu gibi kazanir.
    base = {"a": {"x": 1}}
    overrides = {"a": "replaced"}

    assert _deep_merge(base, overrides) == {"a": "replaced"}


# ---------------------------------------------------------------------------
# _run_seed_command / main() - M1.4 review duzeltmesi: bu iki fonksiyon
# hicbir testte dogrudan cagirilmiyordu, yalnizca alt seviyedeki `seed()`
# yardimcisi test ediliyordu. Gercek `linkedinbot seed` komutunun
# calistirdigi commit/rollback/dispatch mantigi bu yuzden hicbir otomatik
# testte dogrulanmamisti - gercek DB'ye dokunmadan (mocking ile) burada
# kapatilir.
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class _FakeEngine:
    def __init__(self):
        self.disposed = False

    def dispose(self):
        self.disposed = True


def test_run_seed_command_commits_and_closes_on_success(monkeypatch, capsys):
    fake_session = _FakeSession()
    fake_engine = _FakeEngine()
    fake_account = Account(account_id=uuid4(), display_name="Test", created_at=NOW, status="active")

    monkeypatch.setattr(cli, "create_db_engine", lambda: fake_engine)
    monkeypatch.setattr(cli, "create_session_factory", lambda engine: (lambda: fake_session))
    monkeypatch.setattr(cli, "seed", lambda config_dir, session: fake_account)

    cli._run_seed_command(Path("irrelevant"))

    assert fake_session.committed is True
    assert fake_session.rolled_back is False
    assert fake_session.closed is True
    assert fake_engine.disposed is True
    assert str(fake_account.account_id) in capsys.readouterr().out


def test_run_seed_command_rolls_back_closes_and_reraises_on_failure(monkeypatch):
    fake_session = _FakeSession()
    fake_engine = _FakeEngine()

    def _raise(config_dir, session):
        raise ValueError("boom")

    monkeypatch.setattr(cli, "create_db_engine", lambda: fake_engine)
    monkeypatch.setattr(cli, "create_session_factory", lambda engine: (lambda: fake_session))
    monkeypatch.setattr(cli, "seed", _raise)

    with pytest.raises(ValueError, match="boom"):
        cli._run_seed_command(Path("irrelevant"))

    assert fake_session.committed is False
    assert fake_session.rolled_back is True
    assert fake_session.closed is True
    assert fake_engine.disposed is True


def test_main_seed_command_dispatches_to_run_seed_command_with_config_dir(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_run_seed_command", lambda config_dir: calls.append(config_dir))

    exit_code = cli.main(["seed", "--config-dir", "/opt/custom-config"])

    assert exit_code == 0
    assert calls == [Path("/opt/custom-config")]


def test_main_seed_command_defaults_config_dir_to_config(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_run_seed_command", lambda config_dir: calls.append(config_dir))

    cli.main(["seed"])

    assert calls == [Path("config")]
