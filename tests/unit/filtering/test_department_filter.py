"""filtering/department_filter.py icin birim testleri (Roadmap M6.4, FR-4,
PRD Section 11.2, EDGE-2).

Roadmap M6.4 "Amac": "FR-4'u, alti kume ve 0.65 varsayilan esikle, iki
dilli (EDGE-2) olarak uygulamak." "Beklenen Sonuc": "Listede birebir
olmayan ama anlamca yakin unvanlar (TR/EN) dogru guven skoruyla
yakalanir."

Proje talimatiyla acikca onaylanan mimari karar: TDD Section 11.4'un
"borderline" mantigi acikca "Filtering Pipeline" (yani M6.5'in
montajlanmis zinciri) seviyesinde tanimlanir ("Filtreleme asamasi
reddetmez, Filtering Pipeline ciktisi uc degerden birini tasir"), TEK
BIR filtre fonksiyonunun kendisinde degil; ayrica PRD Section 17'nin
konfigurasyon tablosunda Department'a ozel bir "tolerans" parametresi
YOKTUR (yalnizca 0-100 puanlik AI Match Score olceginde tanimli
"Borderline Bant Genisligi" vardir, 0.0-1.0 olcekli Department guvenine
uygulanamaz). Bu yuzden bu filtre, M6.1/M6.2/M6.3 ile AYNI sekilde,
dogrudan esik-uygulanmis bir `FilterResult(passed, reason, confidence)`
doner - borderline ileriye tasima mantigi KASITLI OLARAK burada
UYGULANMAZ (M6.5'in kapsamidir).

LLM Gateway sahte (fake) bir nesneyle test edilir (M6.3'un kendi
deseniyle ayni yaklasim) - gercek Anthropic API'ye HICBIR ZAMAN
dokunulmaz. Gercek/canli semantik dogrulama (Roadmap'in "15-20 basliktan
olusan kuratorlu test seti") ayri bir entegrasyon testinde
(tests/integration/filtering/test_department_filter_live.py) ele alinir.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from linkedinbot.domain.job_posting import JobPosting
from linkedinbot.filtering.department_filter import (
    DepartmentMatchInference,
    filter_by_department,
)

COLLECTED_AT = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
TEST_MODEL = "claude-3-5-haiku-20241022"
CONFIDENCE_THRESHOLD = 0.65
DEPARTMENT_CLUSTERS = {
    "Sales & Business Development": [
        "Sales",
        "Sales Executive",
        "Key Account",
        "Business Development",
    ],
    "Marketing": ["Marketing", "Digital Marketing", "Brand Marketing"],
}


def _job_posting(**overrides) -> JobPosting:
    data = {
        "job_id": "https://www.linkedin.com/jobs/view/1",
        "title": "Sales Executive",
        "company_id": "Acme Corp",
        "location": "Istanbul, Turkey",
        "posted_date": COLLECTED_AT,
        "description": "Managing key accounts and new business development.",
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


def test_confidence_above_threshold_passes_and_reports_the_confidence_score():
    llm_gateway = _FakeLLMGateway(
        result=DepartmentMatchInference(
            matched_cluster="Sales & Business Development",
            confidence=0.9,
            reasoning="Directly matches the Sales & Business Development cluster.",
        )
    )
    job_posting = _job_posting()

    result = filter_by_department(
        job_posting, DEPARTMENT_CLUSTERS, CONFIDENCE_THRESHOLD, llm_gateway, TEST_MODEL
    )

    assert result.passed is True
    assert result.confidence == 0.9
    assert "Sales & Business Development" in result.reason


def test_confidence_below_threshold_is_rejected():
    llm_gateway = _FakeLLMGateway(
        result=DepartmentMatchInference(
            matched_cluster=None,
            confidence=0.2,
            reasoning="No clear relation to any target department.",
        )
    )
    job_posting = _job_posting(
        title="Warehouse Forklift Operator", description="Operate a forklift."
    )

    result = filter_by_department(
        job_posting, DEPARTMENT_CLUSTERS, CONFIDENCE_THRESHOLD, llm_gateway, TEST_MODEL
    )

    assert result.passed is False
    assert result.confidence == 0.2


def test_confidence_exactly_at_threshold_passes():
    # Esik "uzerinde" -> dahil (>=) kabul edilir (PRD 11.2: "esigin
    # UZERINDE olan ilanlar ilerler" - "en az esik kadar" seklinde
    # yorumlanmistir, digerlerinde oldugu gibi acikca aksi belirtilmedigi
    # surece).
    llm_gateway = _FakeLLMGateway(
        result=DepartmentMatchInference(
            matched_cluster="Marketing", confidence=0.65, reasoning="Borderline but matches."
        )
    )
    job_posting = _job_posting()

    result = filter_by_department(
        job_posting, DEPARTMENT_CLUSTERS, CONFIDENCE_THRESHOLD, llm_gateway, TEST_MODEL
    )

    assert result.passed is True


def test_renders_the_department_matching_template_with_clusters_and_job_details():
    llm_gateway = _FakeLLMGateway(
        result=DepartmentMatchInference(
            matched_cluster="Sales & Business Development", confidence=0.9, reasoning="Fits."
        )
    )
    job_posting = _job_posting(
        title="Ticaret Uzman Yardimcisi", description="Uluslararasi ticaret operasyonlari."
    )

    filter_by_department(
        job_posting, DEPARTMENT_CLUSTERS, CONFIDENCE_THRESHOLD, llm_gateway, TEST_MODEL
    )

    assert len(llm_gateway.calls) == 1
    call = llm_gateway.calls[0]
    assert call["template_name"] == "department_matching"
    assert call["response_model"] is DepartmentMatchInference
    assert call["model"] == TEST_MODEL
    assert call["template_variables"]["job_title"] == job_posting.title
    assert call["template_variables"]["job_description"] == job_posting.description
    clusters_text = call["template_variables"]["department_clusters"]
    assert "Sales & Business Development" in clusters_text
    assert "Marketing" in clusters_text
    assert "Digital Marketing" in clusters_text


def test_unavailable_llm_inference_is_rejected_by_default():
    # LLMGateway.generate() None doner (repair de basarisiz oldu) - M5.3/
    # M6.3'un "asla uydurma bir skor uretme" ilkesi burada da gecerlidir.
    llm_gateway = _FakeLLMGateway(result=None)
    job_posting = _job_posting()

    result = filter_by_department(
        job_posting, DEPARTMENT_CLUSTERS, CONFIDENCE_THRESHOLD, llm_gateway, TEST_MODEL
    )

    assert result.passed is False
    assert result.confidence is None
    assert "could not be determined" in result.reason.lower()
