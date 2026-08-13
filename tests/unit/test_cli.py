from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from linkedinbot import cli
from linkedinbot.cli import _deep_merge, validate_config_files
from linkedinbot.config.validator import ConfigValidationError
from linkedinbot.domain.account import Account
from linkedinbot.domain.run_log import RunLog, RunStatus, TriggerType
from linkedinbot.run.orchestrator import RunAlreadyInProgressError

NOW = datetime(2026, 8, 8, tzinfo=UTC)
REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"


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


# ---------------------------------------------------------------------------
# `config validate` (Roadmap M2.4) - `validate_config_files()` gercek repo
# config dosyalarina karsi (test_seed.py'nin ayni REPO_ROOT/config desenini
# kullanarak), ve bilinen-kotu config dosyalari ureten gecici dizinlere
# karsi test edilir. DB'ye hicbir sekilde dokunulmaz (kullanicinin acikca
# onayladigi kapsam: yalnizca config DOSYALARI, DB'deki aktif config degil).
# ---------------------------------------------------------------------------


def _write_config_files(config_dir: Path, system_defaults: dict, account_overrides: dict) -> None:
    (config_dir / "accounts").mkdir(parents=True, exist_ok=True)
    (config_dir / "system.defaults.yaml").write_text(yaml.safe_dump(system_defaults))
    account_seed = {
        "display_name": "Test",
        "career_goals": "goals",
        "skills_summary": "skills",
        "account_config_overrides": account_overrides,
    }
    (config_dir / "accounts" / "default.account.yaml").write_text(yaml.safe_dump(account_seed))


def _minimal_valid_system_defaults() -> dict:
    return {
        "target_criteria": {
            "locations": ["Istanbul"],
            "departments": {"Sales & Business Development": ["Sales Executive"]},
            "experience_levels": ["Entry Level"],
            "workplace_types": ["On-site"],
        },
        "weights_ai_match": {
            "department_role_relevance": 0.35,
            "experience_level_fit": 0.15,
            "location_fit": 0.10,
            "company_quality_contribution": 0.25,
            "career_goal_alignment": 0.15,
        },
        "weights_company_quality": {
            "brand_reputation_prestige": 0.25,
            "company_scale": 0.20,
            "career_development_training_culture": 0.20,
            "sector_position": 0.15,
            "corporate_stability": 0.10,
            "external_signals": 0.10,
        },
        "thresholds": {
            "company_quality_score": 50,
            "ai_match_score": 60,
            "department_confidence": 0.65,
            "department_confidence_tolerance": 0.05,
            "borderline_band_width": 5,
            "company_score_reevaluation_window_days": 30,
            "linkedin_retry_attempts": 3,
            "llm_retry_attempts": 3,
            "retry_base_delay_ms": 500,
            "retry_max_delay_ms": 8000,
            "linkedin_consecutive_failure_threshold": 5,
        },
        "schedule": {"interval_days": 2, "jitter_minutes": 30},
        "collection_limits": {"max_jobs_per_run": 200},
        "notification_settings": {"enabled": False, "channels": []},
        "report_format_settings": {
            "format": "Markdown",
            "template": "default",
            "top_matches_count": 10,
            "language": "en",
        },
        "prompt_template_refs": {
            "department_matching": "department_matching.prompt.md",
            "experience_inference": "experience_inference.prompt.md",
            "company_scoring": "company_scoring.prompt.md",
            "ai_match_rationale": "ai_match_rationale.prompt.md",
        },
    }


def test_validate_config_files_accepts_real_repo_config():
    # M1.4'un zaten onaylanmis, gercekten seed edilen dosyalari - "bilinen
    # iyi config dosyalari" (Roadmap M2.4 Tamamlanma Dogrulamasi) tam
    # olarak budur.
    profile = validate_config_files(CONFIG_DIR)

    assert profile.target_criteria.locations == ["Istanbul"]
    assert profile.report_format_settings.language == "en"


def test_validate_config_files_accepts_known_good_config(tmp_path: Path):
    _write_config_files(tmp_path, _minimal_valid_system_defaults(), {})

    profile = validate_config_files(tmp_path)

    assert profile.thresholds.ai_match_score == 60


def test_validate_config_files_rejects_known_bad_weight_sum(tmp_path: Path):
    bad_defaults = _minimal_valid_system_defaults()
    bad_defaults["weights_ai_match"]["department_role_relevance"] = 0.99  # toplam artik 1.0 degil
    _write_config_files(tmp_path, bad_defaults, {})

    with pytest.raises(ConfigValidationError, match="AI Match Score"):
        validate_config_files(tmp_path)


def test_validate_config_files_rejects_missing_required_field(tmp_path: Path):
    bad_defaults = _minimal_valid_system_defaults()
    del bad_defaults["target_criteria"]["workplace_types"]
    _write_config_files(tmp_path, bad_defaults, {})

    with pytest.raises(ConfigValidationError, match="workplace_types"):
        validate_config_files(tmp_path)


def test_validate_config_files_propagates_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        validate_config_files(tmp_path)


def test_validate_config_files_raises_yaml_error_for_malformed_syntax(tmp_path: Path):
    # Ic-denetimde bulunan bulgu: bir kullanicinin "bilinen kotu config
    # dosyasi" (Roadmap M2.4) olarak deneyecegi en dogal senaryo -
    # sozdizimsel olarak bozuk YAML - ham bir traceback'e neden oluyordu.
    (tmp_path / "accounts").mkdir(parents=True)
    (tmp_path / "system.defaults.yaml").write_text("not: valid: yaml: [unclosed")
    (tmp_path / "accounts" / "default.account.yaml").write_text(
        yaml.safe_dump({"display_name": "x", "career_goals": "x", "skills_summary": "x"})
    )

    with pytest.raises(yaml.YAMLError):
        validate_config_files(tmp_path)


def test_validate_config_files_raises_value_error_for_empty_file(tmp_path: Path):
    # Ayni bulgu, sozdizimsel olarak GECERLI ama bos/mapping-olmayan bir
    # YAML dosyasi icin (yaml.safe_load bos bir dosyadan None doner) -
    # _deep_merge icinde ham bir TypeError'a neden oluyordu.
    (tmp_path / "accounts").mkdir(parents=True)
    (tmp_path / "system.defaults.yaml").write_text("")
    (tmp_path / "accounts" / "default.account.yaml").write_text(
        yaml.safe_dump({"display_name": "x", "career_goals": "x", "skills_summary": "x"})
    )

    with pytest.raises(ValueError, match="system.defaults.yaml"):
        validate_config_files(tmp_path)


def test_run_config_validate_command_returns_zero_and_prints_success_on_valid_config(
    monkeypatch, capsys
):
    monkeypatch.setattr(cli, "validate_config_files", lambda config_dir: object())

    exit_code = cli._run_config_validate_command(Path("some-dir"))

    assert exit_code == 0
    assert "some-dir" in capsys.readouterr().out


def test_run_config_validate_command_returns_one_and_prints_errors_on_invalid_config(
    monkeypatch, capsys
):
    def _raise(config_dir):
        raise ConfigValidationError(["thresholds.ai_match_score: bir sey yanlis"])

    monkeypatch.setattr(cli, "validate_config_files", _raise)

    exit_code = cli._run_config_validate_command(Path("some-dir"))

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "thresholds.ai_match_score" in err


def test_run_config_validate_command_returns_one_and_prints_message_on_missing_file(
    monkeypatch, capsys
):
    def _raise(config_dir):
        raise FileNotFoundError("no such file: system.defaults.yaml")

    monkeypatch.setattr(cli, "validate_config_files", _raise)

    exit_code = cli._run_config_validate_command(Path("some-dir"))

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "system.defaults.yaml" in err


def test_run_config_validate_command_returns_one_and_prints_message_on_malformed_yaml(
    monkeypatch, capsys
):
    def _raise(config_dir):
        raise yaml.YAMLError("mapping values are not allowed here")

    monkeypatch.setattr(cli, "validate_config_files", _raise)

    exit_code = cli._run_config_validate_command(Path("some-dir"))

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "mapping values are not allowed here" in err


def test_run_config_validate_command_returns_one_and_prints_message_on_non_mapping_yaml(
    monkeypatch, capsys
):
    def _raise(config_dir):
        raise ValueError("system.defaults.yaml: gecerli bir YAML sozlugu icermiyor.")

    monkeypatch.setattr(cli, "validate_config_files", _raise)

    exit_code = cli._run_config_validate_command(Path("some-dir"))

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "system.defaults.yaml" in err


def test_run_config_validate_command_config_validation_error_not_swallowed_by_value_error(
    monkeypatch, capsys
):
    # ConfigValidationError, ValueError'un bir alt sinifidir - except
    # sirasi yanlis olursa (genel ValueError once yakalanirsa) `.errors`
    # listesindeki tek tek maddeler yerine genel ValueError mesaji basilir.
    def _raise(config_dir):
        raise ConfigValidationError(["thresholds.ai_match_score: bir sey yanlis"])

    monkeypatch.setattr(cli, "validate_config_files", _raise)

    exit_code = cli._run_config_validate_command(Path("some-dir"))

    err = capsys.readouterr().err
    assert exit_code == 1
    assert "  - thresholds.ai_match_score: bir sey yanlis" in err


def test_main_config_validate_dispatches_with_config_dir(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli, "_run_config_validate_command", lambda config_dir: calls.append(config_dir) or 0
    )

    exit_code = cli.main(["config", "validate", "--config-dir", "/opt/custom-config"])

    assert exit_code == 0
    assert calls == [Path("/opt/custom-config")]


def test_main_config_validate_defaults_config_dir_to_config(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli, "_run_config_validate_command", lambda config_dir: calls.append(config_dir) or 0
    )

    cli.main(["config", "validate"])

    assert calls == [Path("config")]


def test_main_config_validate_propagates_nonzero_exit_code(monkeypatch):
    monkeypatch.setattr(cli, "_run_config_validate_command", lambda config_dir: 1)

    assert cli.main(["config", "validate"]) == 1


# ---------------------------------------------------------------------------
# `run` (Roadmap M9.7, FR-12 manuel tetikleme). `--account` ZORUNLUDUR -
# argumansiz form (TDD Section 12'nin tek satirlik parantez ornegi)
# M9.7'nin KENDI "Beklenen Sonuc"/"Tamamlanma Dogrulamasi" metninde HICBIR
# YERDE gecmez ve FR-12'nin kabul kriterleri de sessizdir; bagimsiz
# dogrulama sonrasi (kullanicinin acikca onayladigi karar) YALNIZCA
# `--account <id>` formu desteklenir - `AccountRepositoryPort`'a
# "tek hesabi bul" gibi yeni bir metod EKLENMEZ.
#
# `_run_run_command()`, GERCEK adaptorleri (Playwright/Anthropic/OS
# keychain) `_build_dependencies()` icinde kurar - bu fonksiyon burada
# monkeypatch ile TAMAMEN degistirilir (tipki `seed()`'in kendi test
# deseninde oldugu gibi), boylece bu testler hicbir gercek dis sisteme
# dokunmaz.
# ---------------------------------------------------------------------------


def _run_log(
    status: RunStatus,
    *,
    error_detail: str | None = None,
    partial_reason: str | None = None,
) -> RunLog:
    return RunLog(
        run_id=uuid4(),
        account_id=uuid4(),
        trigger_type=TriggerType.MANUAL,
        started_at=NOW,
        ended_at=NOW,
        jobs_collected=5,
        jobs_filtered=3,
        jobs_new=2,
        jobs_closed=1,
        status=status,
        error_detail=error_detail,
        partial_reason=partial_reason,
    )


def test_report_run_result_prints_summary_and_returns_zero_for_success(capsys):
    result = _run_log(RunStatus.SUCCESS)

    exit_code = cli._report_run_result(result)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Success" in out
    assert "5" in out and "3" in out and "2" in out and "1" in out


def test_report_run_result_prints_summary_and_returns_zero_for_partial(capsys):
    result = _run_log(RunStatus.PARTIAL, partial_reason="devre kesici tetiklendi")

    exit_code = cli._report_run_result(result)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Partial" in out
    assert "devre kesici tetiklendi" in out


def test_report_run_result_prints_error_detail_and_returns_one_for_failed(capsys):
    result = _run_log(RunStatus.FAILED, error_detail="LinkedIn session expired")

    exit_code = cli._report_run_result(result)

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "LinkedIn session expired" in err


class _FakeSecretsProvider:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self._values = dict(values or {})

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def set(self, key: str, value: str) -> None:
        self._values[key] = value


def test_require_secret_returns_the_value_when_present():
    provider = _FakeSecretsProvider({"anthropic_api_key": "sk-ant-test"})

    assert cli._require_secret(provider, "anthropic_api_key") == "sk-ant-test"


def test_require_secret_raises_value_error_naming_the_key_when_missing():
    provider = _FakeSecretsProvider({})

    with pytest.raises(ValueError, match="anthropic_api_key"):
        cli._require_secret(provider, "anthropic_api_key")


ACCOUNT_ID = uuid4()


def test_run_run_command_commits_and_closes_on_success(monkeypatch, capsys):
    fake_session = _FakeSession()
    fake_engine = _FakeEngine()
    fake_dependencies = object()
    result = _run_log(RunStatus.SUCCESS)

    monkeypatch.setattr(cli, "create_db_engine", lambda: fake_engine)
    monkeypatch.setattr(cli, "create_session_factory", lambda engine: (lambda: fake_session))
    monkeypatch.setattr(
        cli,
        "_build_dependencies",
        lambda account_id, session, config_dir, reports_dir, secrets_file: fake_dependencies,
    )
    monkeypatch.setattr(
        cli, "run_account", lambda account_id, dependencies, now, lock_duration: result
    )

    exit_code = cli._run_run_command(
        ACCOUNT_ID, Path("config"), Path("reports"), Path("secrets.json")
    )

    assert exit_code == 0
    assert fake_session.committed is False  # run_account/orchestrator.run() KENDI commit eder
    assert fake_session.rolled_back is False
    assert fake_session.closed is True
    assert fake_engine.disposed is True
    assert "Success" in capsys.readouterr().out


def test_run_run_command_prints_message_and_returns_one_when_already_running(
    monkeypatch, capsys
):
    fake_session = _FakeSession()
    fake_engine = _FakeEngine()

    def _raise_already_running(account_id, dependencies, now, lock_duration):
        raise RunAlreadyInProgressError(f"Hesap icin zaten bir calistirma suruyor: {account_id}")

    monkeypatch.setattr(cli, "create_db_engine", lambda: fake_engine)
    monkeypatch.setattr(cli, "create_session_factory", lambda engine: (lambda: fake_session))
    monkeypatch.setattr(
        cli,
        "_build_dependencies",
        lambda account_id, session, config_dir, reports_dir, secrets_file: object(),
    )
    monkeypatch.setattr(cli, "run_account", _raise_already_running)

    exit_code = cli._run_run_command(
        ACCOUNT_ID, Path("config"), Path("reports"), Path("secrets.json")
    )

    assert exit_code == 1
    assert fake_session.rolled_back is True
    assert fake_session.closed is True
    assert fake_engine.disposed is True
    assert "zaten bir calistirma suruyor" in capsys.readouterr().err


def test_run_run_command_prints_message_and_returns_one_on_value_error(monkeypatch, capsys):
    fake_session = _FakeSession()
    fake_engine = _FakeEngine()

    monkeypatch.setattr(cli, "create_db_engine", lambda: fake_engine)
    monkeypatch.setattr(cli, "create_session_factory", lambda engine: (lambda: fake_session))

    def _raise_value_error(account_id, session, config_dir, reports_dir, secrets_file):
        raise ValueError("Secret bulunamadi: 'anthropic_api_key'")

    monkeypatch.setattr(cli, "_build_dependencies", _raise_value_error)

    exit_code = cli._run_run_command(
        ACCOUNT_ID, Path("config"), Path("reports"), Path("secrets.json")
    )

    assert exit_code == 1
    assert fake_session.rolled_back is True
    assert fake_session.closed is True
    assert fake_engine.disposed is True
    assert "anthropic_api_key" in capsys.readouterr().err


def test_run_run_command_rolls_back_closes_and_reraises_on_unexpected_error(monkeypatch):
    fake_session = _FakeSession()
    fake_engine = _FakeEngine()

    def _raise_unexpected(account_id, session, config_dir, reports_dir, secrets_file):
        raise RuntimeError("unexpected boom")

    monkeypatch.setattr(cli, "create_db_engine", lambda: fake_engine)
    monkeypatch.setattr(cli, "create_session_factory", lambda engine: (lambda: fake_session))
    monkeypatch.setattr(cli, "_build_dependencies", _raise_unexpected)

    with pytest.raises(RuntimeError, match="unexpected boom"):
        cli._run_run_command(ACCOUNT_ID, Path("config"), Path("reports"), Path("secrets.json"))

    assert fake_session.rolled_back is True
    assert fake_session.closed is True
    assert fake_engine.disposed is True


def test_main_run_command_dispatches_with_account_and_defaults(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli,
        "_run_run_command",
        lambda account_id, config_dir, reports_dir, secrets_file: calls.append(
            (account_id, config_dir, reports_dir, secrets_file)
        )
        or 0,
    )

    exit_code = cli.main(["run", "--account", str(ACCOUNT_ID)])

    assert exit_code == 0
    assert calls == [(ACCOUNT_ID, Path("config"), Path("reports"), Path("secrets.json"))]


def test_main_run_command_accepts_custom_paths(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli,
        "_run_run_command",
        lambda account_id, config_dir, reports_dir, secrets_file: calls.append(
            (account_id, config_dir, reports_dir, secrets_file)
        )
        or 0,
    )

    cli.main(
        [
            "run",
            "--account",
            str(ACCOUNT_ID),
            "--config-dir",
            "/opt/custom-config",
            "--reports-dir",
            "/opt/reports",
            "--secrets-file",
            "/opt/secrets.json",
        ]
    )

    assert calls == [
        (ACCOUNT_ID, Path("/opt/custom-config"), Path("/opt/reports"), Path("/opt/secrets.json"))
    ]


def test_main_run_command_requires_account_argument():
    with pytest.raises(SystemExit):
        cli.main(["run"])


def test_main_run_command_propagates_nonzero_exit_code(monkeypatch):
    monkeypatch.setattr(
        cli, "_run_run_command", lambda account_id, config_dir, reports_dir, secrets_file: 1
    )

    assert cli.main(["run", "--account", str(ACCOUNT_ID)]) == 1
