"""PromptRegistry icin birim testleri (Roadmap M5.2).

Roadmap M5.2 "Tamamlanma Dogrulamasi": "Birim testi her sablonun ornek
degiskenlerle dogru render edildigini dogrular."

Iki grup test var:
1. Mekanizma testleri (`tmp_path` ile izole, sentetik sablon dosyalari) -
   `PromptRegistry`'nin genel yukleme/render/hata davranisini, gercek
   prompt icerigine bagli olmadan dogrular.
2. Gercek sablon testleri (`config/prompts/` altindaki GERCEK dort dosya) -
   test_seed.py'nin (M1.4) "sentetik fixture degil, bu milestone'un
   gercekten teslim ettigi dosyalar kullanilir" desenini birebir izler.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from linkedinbot.adapters.llm.prompt_registry import PromptRegistry

REPO_ROOT = Path(__file__).resolve().parents[4]
PROMPTS_DIR = REPO_ROOT / "config" / "prompts"


# ---------------------------------------------------------------------------
# Mekanizma testleri (izole, sentetik sablonlar)
# ---------------------------------------------------------------------------


def test_render_substitutes_given_variables_into_the_template_file(tmp_path):
    (tmp_path / "greeting.prompt.md").write_text(
        "Hello, ${name}! Your score is ${score}.", encoding="utf-8"
    )
    registry = PromptRegistry(tmp_path)

    result = registry.render("greeting", name="Ada", score="42")

    assert result == "Hello, Ada! Your score is 42."


def test_render_raises_file_not_found_for_unknown_template_name(tmp_path):
    registry = PromptRegistry(tmp_path)

    with pytest.raises(FileNotFoundError):
        registry.render("does_not_exist", name="Ada")


def test_render_raises_key_error_when_a_placeholder_variable_is_missing(tmp_path):
    (tmp_path / "greeting.prompt.md").write_text("Hello, ${name}!", encoding="utf-8")
    registry = PromptRegistry(tmp_path)

    with pytest.raises(KeyError):
        registry.render("greeting")


def test_render_ignores_extra_unused_variables(tmp_path):
    (tmp_path / "greeting.prompt.md").write_text("Hello, ${name}!", encoding="utf-8")
    registry = PromptRegistry(tmp_path)

    result = registry.render("greeting", name="Ada", unused="ignored")

    assert result == "Hello, Ada!"


# ---------------------------------------------------------------------------
# Gercek sablon testleri (config/prompts/*.prompt.md)
# ---------------------------------------------------------------------------


def test_department_matching_template_renders_with_example_variables():
    registry = PromptRegistry(PROMPTS_DIR)

    result = registry.render(
        "department_matching",
        job_title="Sales Executive",
        job_description="Responsible for managing key accounts and new business development.",
        department_clusters=(
            "Sales & Business Development: Sales, Sales Executive, Key Account, "
            "Account Management, Business Development"
        ),
    )

    assert "Sales Executive" in result
    assert "managing key accounts" in result
    assert "Sales & Business Development" in result
    assert "${" not in result


def test_experience_inference_template_renders_with_example_variables():
    registry = PromptRegistry(PROMPTS_DIR)

    result = registry.render(
        "experience_inference",
        job_title="Junior Business Analyst",
        job_description="Looking for a recent graduate to join our analytics team.",
        accepted_experience_levels="Internship, New Graduate, Entry Level, Junior",
    )

    assert "Junior Business Analyst" in result
    assert "recent graduate to join our analytics team" in result
    assert "Internship, New Graduate, Entry Level, Junior" in result
    assert "${" not in result


def test_company_scoring_template_renders_with_example_variables():
    registry = PromptRegistry(PROMPTS_DIR)

    result = registry.render(
        "company_scoring",
        company_name="Acme Corp",
        company_context=(
            "Founded in 1998, ~2000 employees, publicly listed, operates in 15 countries."
        ),
    )

    assert "Acme Corp" in result
    assert "Founded in 1998" in result
    assert "${" not in result


def test_ai_match_rationale_template_renders_with_example_variables():
    registry = PromptRegistry(PROMPTS_DIR)

    result = registry.render(
        "ai_match_rationale",
        department_relevance_score="0.9",
        department_relevance_note="Matches Business Development cluster closely.",
        experience_level_fit_note="Matches Entry Level.",
        location_fit_note="Located in Istanbul.",
        company_quality_score="88",
        career_goal_alignment_score="0.8",
        career_goal_alignment_note="Aligned with stated interest in commercial roles.",
    )

    assert "0.9" in result
    assert "Matches Business Development cluster closely." in result
    assert "Matches Entry Level." in result
    assert "Located in Istanbul." in result
    assert "88" in result
    assert "0.8" in result
    assert "Aligned with stated interest in commercial roles." in result
    assert "${" not in result
