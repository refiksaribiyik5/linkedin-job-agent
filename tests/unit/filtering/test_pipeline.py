"""filtering/pipeline.py icin birim testleri (Roadmap M6.5, TDD Section
11.4).

Roadmap M6.5 "Beklenen Sonuc": "Karma bir ilan grubu tek bir cagriyla
sirayla filtrelenir; her ilan icin FilterResultDetail uretilir."
"Tamamlanma Dogrulamasi": "Entegrasyon testi, elle hesaplanmis beklenen
pass/reject/borderline dagilimiyla karsilastirilir."

Proje talimatiyla acikca onaylanan mimari kararlar:
- Zincir SIRAYLA ve KISA DEVRE ILE calisir (Blacklist -> Location ->
  Experience -> Department): bir asama reddederse SONRAKI asamalar HIC
  CAGRILMAZ - TDD Section 11.4'un "maliyet-sirali filtreleme" ve "AI
  cagrisini en son, en ucuz filtrelerden sonra calistir" ilkeleriyle
  tutarlidir (Deneyim/Departman LLM cagrisi gerektirebilir; erken
  reddedilen bir ilan icin bu maliyete hic girilmez).
- `PipelineResult.passed`/`is_borderline` ayrimi, `EvaluatedJob`'un
  (M1.1) zaten kurdugu "borderline, durum enum'unun bir kolu degil, ayri
  bir boolean bayraktir" desenini birebir izler: borderline bir ilan
  passed=True (bir sonraki asamaya ilerler) VE is_borderline=True olarak
  isaretlenir - TDD'nin "ilan yine de bir sonraki asamaya... ilerler"
  ifadesiyle tutarlidir.
- `department_confidence_tolerance`, KULLANICI KARARIYLA acikca
  onaylandigi uzere, dogrudan cagirana birakilan duz bir parametredir -
  hicbir yerde sabit-kodlanmaz, config/varsayilan olarak eklenmez. Bu
  test dosyasindaki `0.05` degeri SADECE test verisidir, bir proje
  varsayilani veya is kurali degildir.

LLM Gateway sahte (fake) bir nesneyle test edilir - gercek Anthropic
API'ye HICBIR ZAMAN dokunulmaz.
"""

from __future__ import annotations

from datetime import UTC, datetime

from linkedinbot.domain.job_posting import JobPosting
from linkedinbot.domain.user_profile import Preferences
from linkedinbot.filtering.department_filter import DepartmentMatchInference
from linkedinbot.filtering.experience_filter import ExperienceLevelInference
from linkedinbot.filtering.pipeline import PipelineResult, run_filtering_pipeline

COLLECTED_AT = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
TEST_MODEL = "claude-3-5-haiku-20241022"

TARGET_LOCATIONS = ["Istanbul"]
ACCEPTED_EXPERIENCE_LEVELS = ["Entry Level", "Internship", "New Graduate", "Junior"]
DEPARTMENT_CLUSTERS = {
    "Sales & Business Development": ["Sales", "Sales Executive", "Business Development"],
}
DEPARTMENT_CONFIDENCE_THRESHOLD = 0.65
DEPARTMENT_CONFIDENCE_TOLERANCE = 0.05  # yalnizca test verisi, bir varsayilan/is kurali DEGIL.


def _job_posting(**overrides) -> JobPosting:
    data = {
        "job_id": "https://www.linkedin.com/jobs/view/1",
        "title": "Sales Executive",
        "company_id": "Acme Corp",
        "location": "Istanbul, Turkey",
        "posted_date": COLLECTED_AT,
        "description": "Entry Level role managing key accounts.",
        "application_url": "https://www.linkedin.com/jobs/view/1",
        "collected_at": COLLECTED_AT,
    }
    data.update(overrides)
    return JobPosting(**data)


class _StubLLMGateway:
    """Sablon adina gore (experience_inference / department_matching) VE
    ilanin basligina gore sabit bir yanit donen sahte Gateway - M5.3/M6.3/
    M6.4'un tekli-sonuc sahtelerinden farkli olarak, tek bir cagrida
    BIRDEN FAZLA ilan/asama icin FARKLI yanitlar gerektiren "karma bir ilan
    grubu" senaryosunu test edebilmek icin tablo-tabanlidir."""

    def __init__(self, experience_by_title=None, department_by_title=None):
        self._experience_by_title = experience_by_title or {}
        self._department_by_title = department_by_title or {}
        self.calls: list[dict] = []

    def generate(self, template_name, response_model, model, **template_variables):
        self.calls.append(
            {
                "template_name": template_name,
                "response_model": response_model,
                "model": model,
                **template_variables,
            }
        )
        job_title = template_variables["job_title"]
        if template_name == "experience_inference":
            return self._experience_by_title[job_title]
        if template_name == "department_matching":
            return self._department_by_title[job_title]
        raise AssertionError(f"unexpected template_name: {template_name}")


def _run_one(job_posting: JobPosting, llm_gateway) -> PipelineResult:
    preferences = Preferences(excluded_companies=["Blacklisted Co"], excluded_job_ids=[])
    results = run_filtering_pipeline(
        [job_posting],
        preferences,
        TARGET_LOCATIONS,
        ACCEPTED_EXPERIENCE_LEVELS,
        DEPARTMENT_CLUSTERS,
        DEPARTMENT_CONFIDENCE_THRESHOLD,
        DEPARTMENT_CONFIDENCE_TOLERANCE,
        llm_gateway,
        TEST_MODEL,
    )
    assert len(results) == 1
    posting, result = results[0]
    assert posting is job_posting
    return result


def test_blacklisted_job_is_rejected_without_calling_later_filters():
    job_posting = _job_posting(company_id="Blacklisted Co")
    llm_gateway = _StubLLMGateway()

    result = _run_one(job_posting, llm_gateway)

    assert result.passed is False
    assert result.is_borderline is False
    assert set(result.filter_result_detail) == {"blacklist"}
    assert llm_gateway.calls == []


def test_out_of_location_job_is_rejected_without_calling_later_filters():
    job_posting = _job_posting(location="Ankara, Turkey")
    llm_gateway = _StubLLMGateway()

    result = _run_one(job_posting, llm_gateway)

    assert result.passed is False
    assert result.is_borderline is False
    assert set(result.filter_result_detail) == {"blacklist", "location"}
    assert llm_gateway.calls == []


def test_disqualified_experience_job_is_rejected_without_calling_department():
    job_posting = _job_posting(title="Team Lead", description="Leading a small team.")
    llm_gateway = _StubLLMGateway()

    result = _run_one(job_posting, llm_gateway)

    assert result.passed is False
    assert result.is_borderline is False
    assert set(result.filter_result_detail) == {"blacklist", "location", "experience"}
    assert llm_gateway.calls == []


def test_ambiguous_experience_case_is_routed_through_the_pipelines_llm_gateway_correctly():
    # M6.5 review finding (Minor): hicbir mevcut test, Deneyim asamasinin
    # LLM-fallback cagri noktasini pipeline UZERINDEN calistirmiyordu -
    # digerlerinin hepsi kural-tabanli sinyalle cozuluyordu. Bu test,
    # ne kabul-listesi ne de disqualifying bir sinyal tasimayan (M6.3'un
    # kendi "belirsiz durum" fixture'iyla AYNI) bir baslik/aciklama
    # kullanarak LLM yoluna GERCEKTEN dusulmesini VE pipeline'in dogru
    # `accepted_experience_levels`/`model`/`response_model` degerlerini bu
    # cagri noktasina dogru sekilde ilettigini dogrular.
    job_posting = _job_posting(
        title="Business Development Associate",
        description="Join our commercial team and grow with us.",
    )
    llm_gateway = _StubLLMGateway(
        experience_by_title={
            "Business Development Associate": ExperienceLevelInference(
                matches_accepted_level=True, reasoning="Entry-level tone."
            )
        },
        department_by_title={
            "Business Development Associate": DepartmentMatchInference(
                matched_cluster="Sales & Business Development", confidence=0.9, reasoning="Fits."
            )
        },
    )

    result = _run_one(job_posting, llm_gateway)

    assert result.passed is True
    experience_calls = [
        call for call in llm_gateway.calls if call["template_name"] == "experience_inference"
    ]
    assert len(experience_calls) == 1
    call = experience_calls[0]
    assert call["response_model"] is ExperienceLevelInference
    assert call["model"] == TEST_MODEL
    assert call["job_title"] == job_posting.title
    assert call["job_description"] == job_posting.description
    assert call["accepted_experience_levels"] == ", ".join(ACCEPTED_EXPERIENCE_LEVELS)


def test_job_passing_all_four_filters_is_accepted_and_not_borderline():
    job_posting = _job_posting()
    llm_gateway = _StubLLMGateway(
        department_by_title={
            "Sales Executive": DepartmentMatchInference(
                matched_cluster="Sales & Business Development",
                confidence=0.9,
                reasoning="Directly matches.",
            )
        }
    )

    result = _run_one(job_posting, llm_gateway)

    assert result.passed is True
    assert result.is_borderline is False
    assert set(result.filter_result_detail) == {"blacklist", "location", "experience", "department"}


def test_department_confidence_within_tolerance_below_threshold_is_borderline():
    # esik 0.65, tolerans 0.05 -> [0.60, 0.65) araligi borderline.
    job_posting = _job_posting()
    llm_gateway = _StubLLMGateway(
        department_by_title={
            "Sales Executive": DepartmentMatchInference(
                matched_cluster="Sales & Business Development",
                confidence=0.62,
                reasoning="Close but not certain.",
            )
        }
    )

    result = _run_one(job_posting, llm_gateway)

    assert result.passed is True
    assert result.is_borderline is True


def test_department_confidence_below_tolerance_band_is_rejected_outright():
    job_posting = _job_posting()
    llm_gateway = _StubLLMGateway(
        department_by_title={
            "Sales Executive": DepartmentMatchInference(
                matched_cluster=None, confidence=0.2, reasoning="No relation."
            )
        }
    )

    result = _run_one(job_posting, llm_gateway)

    assert result.passed is False
    assert result.is_borderline is False


def test_unavailable_department_inference_is_rejected_outright_not_borderline():
    # `department_result.confidence` None olabilir (Gateway'in repair
    # denemesi de basarisiz oldu, bkz. department_filter.py M6.4) - bu,
    # pipeline'in "confidence is not None" korumasini (borderline
    # karsilastirmasindan ONCE) fiilen calistiran TEK test. Bu koruma
    # olmasaydi `None >= float` bir TypeError firlatirdi.
    job_posting = _job_posting()
    llm_gateway = _StubLLMGateway(department_by_title={"Sales Executive": None})

    result = _run_one(job_posting, llm_gateway)

    assert result.passed is False
    assert result.is_borderline is False
    assert result.filter_result_detail["department"].confidence is None


def test_filters_a_mixed_batch_of_postings_in_one_call_matching_manually_computed_distribution():
    # Roadmap M6.5'in kendi Tamamlanma Dogrulamasi: "elle hesaplanmis
    # beklenen pass/reject/borderline dagilimiyla karsilastirilir."
    blacklisted = _job_posting(
        job_id="https://www.linkedin.com/jobs/view/1",
        application_url="https://www.linkedin.com/jobs/view/1",
        title="Sales Executive",
        company_id="Blacklisted Co",
    )
    wrong_location = _job_posting(
        job_id="https://www.linkedin.com/jobs/view/2",
        application_url="https://www.linkedin.com/jobs/view/2",
        title="Business Development Rep",
        location="Ankara, Turkey",
    )
    senior_title = _job_posting(
        job_id="https://www.linkedin.com/jobs/view/3",
        application_url="https://www.linkedin.com/jobs/view/3",
        title="Team Lead",
        description="Leading a small team.",
    )
    clean_pass = _job_posting(
        job_id="https://www.linkedin.com/jobs/view/4",
        application_url="https://www.linkedin.com/jobs/view/4",
        title="Clean Pass Candidate",
    )
    borderline_department = _job_posting(
        job_id="https://www.linkedin.com/jobs/view/5",
        application_url="https://www.linkedin.com/jobs/view/5",
        title="Borderline Department Candidate",
    )
    department_reject = _job_posting(
        job_id="https://www.linkedin.com/jobs/view/6",
        application_url="https://www.linkedin.com/jobs/view/6",
        title="Department Reject Candidate",
    )

    llm_gateway = _StubLLMGateway(
        department_by_title={
            "Clean Pass Candidate": DepartmentMatchInference(
                matched_cluster="Sales & Business Development", confidence=0.9, reasoning="Fits."
            ),
            "Borderline Department Candidate": DepartmentMatchInference(
                matched_cluster="Sales & Business Development",
                confidence=0.62,
                reasoning="Close.",
            ),
            "Department Reject Candidate": DepartmentMatchInference(
                matched_cluster=None, confidence=0.1, reasoning="Unrelated."
            ),
        }
    )
    preferences = Preferences(excluded_companies=["Blacklisted Co"], excluded_job_ids=[])

    results = run_filtering_pipeline(
        [
            blacklisted,
            wrong_location,
            senior_title,
            clean_pass,
            borderline_department,
            department_reject,
        ],
        preferences,
        TARGET_LOCATIONS,
        ACCEPTED_EXPERIENCE_LEVELS,
        DEPARTMENT_CLUSTERS,
        DEPARTMENT_CONFIDENCE_THRESHOLD,
        DEPARTMENT_CONFIDENCE_TOLERANCE,
        llm_gateway,
        TEST_MODEL,
    )

    outcomes = {
        posting.title: (result.passed, result.is_borderline) for posting, result in results
    }
    # Elle hesaplanmis beklenen dagilim:
    assert outcomes == {
        "Sales Executive": (False, False),  # blacklist
        "Business Development Rep": (False, False),  # location
        "Team Lead": (False, False),  # experience
        "Clean Pass Candidate": (True, False),  # temiz gecis
        "Borderline Department Candidate": (True, True),  # borderline
        "Department Reject Candidate": (False, False),  # department (kesin red)
    }
    # Sira, girdi sirasiyla AYNI olmali.
    assert [posting.title for posting, _ in results] == [
        "Sales Executive",
        "Business Development Rep",
        "Team Lead",
        "Clean Pass Candidate",
        "Borderline Department Candidate",
        "Department Reject Candidate",
    ]
