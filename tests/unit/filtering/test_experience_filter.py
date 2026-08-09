"""filtering/experience_filter.py icin birim testleri (Roadmap M6.3, FR-5,
PRD Section 11.3, EDGE-1, EDGE-12).

Roadmap M6.3 "Tamamlanma Dogrulamasi": "Birim testleri: acik kidemli
baslik -> red; Management Trainee -> kabul; celiskili baslik/aciklama ->
aciklamaya gore kabul; belirsiz durum -> LLM yoluna (mock) yonlendirilir."

Proje talimatiyla acikca onaylanan mimari kararlar (bkz. modul dokumani):
- TDD Section 11.4'un acik ifadesi geregi (filtreleme asamasi Location/
  Experience/Blacklist icin KESIN passed/rejected doner, borderline
  yalnizca Department icindir), bu filtre `confidence` alanini hep None
  birakir ve EDGE-1'in "borderline bucket" ifadesini uygulamaz.
- Kural tabanli sinyal seti (3+ years / Manager / Team Lead / Management
  Trainee istisnasi) dogrudan PRD 11.3'un kendi ornekleri VE M5.2'nin
  zaten onaylanmis `experience_inference.prompt.md` sablonunun ayni
  ornekleriyle birebir tutarlidir - yeni bir anahtar kelime ICAT
  EDILMEMISTIR.
- LLM Gateway sahte (fake) bir nesneyle test edilir (M5.3'un kendi
  `_ScriptedProvider` deseniyle ayni yaklasim) - gercek Anthropic API'ye
  HICBIR ZAMAN dokunulmaz.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from linkedinbot.domain.job_posting import JobPosting
from linkedinbot.filtering.experience_filter import (
    ExperienceLevelInference,
    filter_by_experience_level,
)

COLLECTED_AT = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
ACCEPTED_LEVELS = [
    "Internship",
    "New Graduate",
    "Entry Level",
    "Graduate Program",
    "Management Trainee",
    "MT Program",
    "0-2 Years Experience",
    "Junior",
]
TEST_MODEL = "claude-3-5-haiku-20241022"


def _job_posting(**overrides) -> JobPosting:
    data = {
        "job_id": "https://www.linkedin.com/jobs/view/1",
        "title": "Sales Executive",
        "company_id": "Acme Corp",
        "location": "Istanbul, Turkey",
        "posted_date": COLLECTED_AT,
        "description": "Entry Level role for recent graduates.",
        "application_url": "https://www.linkedin.com/jobs/view/1",
        "collected_at": COLLECTED_AT,
    }
    data.update(overrides)
    return JobPosting(**data)


class _FakeLLMGateway:
    def __init__(self, result: BaseModel | None):
        self._result = result
        self.calls: list[dict] = []

    def generate(self, template_name, response_model, model, **template_variables):
        self.calls.append(
            {
                "template_name": template_name,
                "response_model": response_model,
                "model": model,
                "template_variables": template_variables,
            }
        )
        return self._result


def test_explicit_seniority_title_is_rejected_without_calling_the_llm():
    job_posting = _job_posting(title="Team Lead - Sales", description="Leading a small team.")
    llm_gateway = _FakeLLMGateway(result=None)

    result = filter_by_experience_level(job_posting, ACCEPTED_LEVELS, llm_gateway, TEST_MODEL)

    assert result.passed is False
    assert llm_gateway.calls == []


def test_explicit_years_of_experience_in_description_is_rejected_without_calling_the_llm():
    job_posting = _job_posting(
        title="Business Analyst", description="Requires 5+ years of experience."
    )
    llm_gateway = _FakeLLMGateway(result=None)

    result = filter_by_experience_level(job_posting, ACCEPTED_LEVELS, llm_gateway, TEST_MODEL)

    assert result.passed is False
    assert llm_gateway.calls == []


def test_management_trainee_title_is_accepted_without_calling_the_llm():
    # PRD 11.3'un acikca adlandirdigi istisna: "Manager" kelimesi ("Management
    # Trainee" icinde degil ama aciklamada) gecse dahi program elenmez.
    job_posting = _job_posting(
        title="Management Trainee Program",
        description="You will report to a Regional Manager during your rotation.",
    )
    llm_gateway = _FakeLLMGateway(result=None)

    result = filter_by_experience_level(job_posting, ACCEPTED_LEVELS, llm_gateway, TEST_MODEL)

    assert result.passed is True
    assert llm_gateway.calls == []


def test_genuinely_conflicting_title_and_description_is_accepted_based_on_description():
    # EDGE-12: baslik KENDI BASINA disqualifying bir sinyal tasir ("Team
    # Lead" -> False), ama aciklama acikca "Entry Level" diyor (True) - bu
    # GERCEK bir celiskidir (iki taraf da FARKLI, None-olmayan bir sinyal
    # verir); aciklama kazanmalidir. (Onceki surumdeki test, basligin
    # "Junior Analyst" olmasi nedeniyle basligin KENDISI ZATEN True
    # dondugunden gercek bir celiski test ETMIYORDU - bkz. self-review.)
    job_posting = _job_posting(
        title="Team Lead", description="This is an Entry Level position for recent graduates."
    )
    llm_gateway = _FakeLLMGateway(result=None)

    result = filter_by_experience_level(job_posting, ACCEPTED_LEVELS, llm_gateway, TEST_MODEL)

    assert result.passed is True
    assert llm_gateway.calls == []


def test_genuinely_conflicting_title_and_description_is_rejected_based_on_description():
    # EDGE-12'nin ters yonu: baslik KENDI BASINA kabul edilen bir seviyeyi
    # isaret eder ("Junior" -> True), ama aciklama acikca disqualifying bir
    # sinyal icerir (5+ years -> False) - aciklama yine kazanmalidir.
    job_posting = _job_posting(
        title="Junior Analyst", description="Requires 5+ years of relevant experience."
    )
    llm_gateway = _FakeLLMGateway(result=None)

    result = filter_by_experience_level(job_posting, ACCEPTED_LEVELS, llm_gateway, TEST_MODEL)

    assert result.passed is False
    assert llm_gateway.calls == []


def test_ambiguous_case_is_routed_to_the_llm_gateway_and_accepted():
    job_posting = _job_posting(
        title="Business Development Associate",
        description="Join our commercial team and grow with us.",
    )
    llm_gateway = _FakeLLMGateway(
        result=ExperienceLevelInference(matches_accepted_level=True, reasoning="Entry-level tone.")
    )

    result = filter_by_experience_level(job_posting, ACCEPTED_LEVELS, llm_gateway, TEST_MODEL)

    assert result.passed is True
    assert len(llm_gateway.calls) == 1
    call = llm_gateway.calls[0]
    assert call["template_name"] == "experience_inference"
    assert call["response_model"] is ExperienceLevelInference
    assert call["model"] == TEST_MODEL
    assert call["template_variables"]["job_title"] == job_posting.title
    assert call["template_variables"]["job_description"] == job_posting.description
    for level in ACCEPTED_LEVELS:
        assert level in call["template_variables"]["accepted_experience_levels"]


def test_ambiguous_case_is_routed_to_the_llm_gateway_and_rejected():
    job_posting = _job_posting(
        title="Business Development Associate",
        description="Join our commercial team and grow with us.",
    )
    llm_gateway = _FakeLLMGateway(
        result=ExperienceLevelInference(
            matches_accepted_level=False, reasoning="Implies prior industry experience."
        )
    )

    result = filter_by_experience_level(job_posting, ACCEPTED_LEVELS, llm_gateway, TEST_MODEL)

    assert result.passed is False
    assert len(llm_gateway.calls) == 1


def test_ambiguous_case_with_unavailable_llm_inference_is_rejected_by_default():
    # LLMGateway.generate() None doner (repair de basarisiz oldu) - M5.3'un
    # "asla uydurma bir skor uretme" ilkesi burada da gecerlidir: sessizce
    # kabul EDILMEZ, varsayilan olarak dislanir ve nedeni acikca belirtilir.
    job_posting = _job_posting(
        title="Business Development Associate",
        description="Join our commercial team and grow with us.",
    )
    llm_gateway = _FakeLLMGateway(result=None)

    result = filter_by_experience_level(job_posting, ACCEPTED_LEVELS, llm_gateway, TEST_MODEL)

    assert result.passed is False
    assert "could not be determined" in result.reason.lower()


def test_experience_filter_never_sets_a_confidence_value():
    # `title="Team Lead"` alone YETERSIZDIR: `_job_posting()`'in varsayilan
    # `description`'i ("Entry Level role for recent graduates.") EDGE-12
    # onceligi geregi kabul sinyaline doner ve rejection dalini hic
    # calistirmaz (bkz. self-review bulgusu). Aciklama da acikca
    # disqualifying/sinyal-siz tutularak (mevcut, ayrica dogrulanmis
    # `test_explicit_seniority_title_is_rejected_without_calling_the_llm`
    # fixture'iyla AYNI) GERCEKTEN red dalinin calistigi garanti edilir.
    rule_based = filter_by_experience_level(
        _job_posting(title="Team Lead", description="Leading a small team."),
        ACCEPTED_LEVELS,
        _FakeLLMGateway(result=None),
        TEST_MODEL,
    )
    assert rule_based.passed is False
    llm_based = filter_by_experience_level(
        _job_posting(title="Business Development Associate", description="Grow with us."),
        ACCEPTED_LEVELS,
        _FakeLLMGateway(
            result=ExperienceLevelInference(matches_accepted_level=True, reasoning="Fits.")
        ),
        TEST_MODEL,
    )

    assert rule_based.confidence is None
    assert llm_based.confidence is None
