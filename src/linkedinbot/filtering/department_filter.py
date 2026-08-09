"""Department Relevance Filter - FR-4, PRD Section 11.2, EDGE-2 (Roadmap
M6.4).

**Semantik esleme, tamamen LLM Gateway'e devredilir:** Bu filtre,
`config/prompts/department_matching.prompt.md` (M5.2, zaten onaylanmis)
sablonunu, `LLMGateway.generate()` (M5.3) araciligiyla cagirir. Iki dilli
(TR/EN) semantik yakinlik tanima (EDGE-2), sablonun kendi talimatinda
zaten acikca istenir ("including Turkish-language or localized title
variants should still be recognized") - bu filtre fonksiyonunun kendisi
HICBIR dil-ozel mantik ICERMEZ, TDD Section 10'un "LLM sinyal cikarir,
kod skoru hesaplar" ilkesiyle tutarli olarak.

**Esik uygulamasi kodda yapilir, LLM'de degil:** Sablonun kendi metni
acikca belirtir: "Do not decide whether the job passes or fails any
threshold... The threshold decision is made separately, outside of this
evaluation." Bu yuzden LLM yalnizca (kume, guven skoru, gerekce)
sinyalini uretir; bu modul, verilen `confidence_threshold` (config'ten,
varsayilan 0.65 - PRD Section 17) ile karsilastirip `passed: bool`
kararini VERIR.

**Neden burada "borderline" mantigi YOKTUR (proje talimatiyla acikca
onaylanan mimari karar):** TDD Section 11.4'un "Borderline mantigi"
pasaji, uc-degerli (passed/rejected/borderline) ciktiyi ACIKCA
`Filtering Pipeline` (yani M6.5'in montajlanmis zincirinin) seviyesine
atfeder ("Filtreleme asamasi reddetmez, Filtering Pipeline ciktisi uc
degerden birini tasir") - TEK BIR filtre fonksiyonuna degil. Ayrica PRD
Section 17'nin konfigurasyon tablosunda Department'a ozel bir "tolerans"
parametresi YOKTUR - yalnizca 0-100 PUAN olcekli AI Match Score icin
tanimli "Borderline Bant Genisligi" vardir (FR-16), bu da 0.0-1.0
olcekli Department guvenine dogrudan uygulanamaz. Bu yuzden bu filtre,
M6.1/M6.2/M6.3 ile AYNI sekilde dogrudan esik-uygulanmis, KESIN bir
`FilterResult` doner; olasi "borderline'a ileri tasima" davranisi M6.5'in
kapsamidir.

**LLM cagrisi basarisiz olursa (Gateway None doner):** M6.3'un kendi
ayni "asla uydurma bir skor uretme" ilkesiyle tutarli olarak, varsayilan
olarak reddedilir (bir skor UYDURULMAZ), `confidence=None` birakilir ve
neden acikca belirtilir.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from linkedinbot.adapters.llm.gateway import LLMGateway
from linkedinbot.domain.evaluated_job import FilterResult
from linkedinbot.domain.job_posting import JobPosting


class DepartmentMatchInference(BaseModel):
    matched_cluster: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


def _format_department_clusters(department_clusters: dict[str, list[str]]) -> str:
    return "\n".join(
        f"{cluster}: {', '.join(titles)}" for cluster, titles in department_clusters.items()
    )


def filter_by_department(
    job_posting: JobPosting,
    department_clusters: dict[str, list[str]],
    confidence_threshold: float,
    llm_gateway: LLMGateway,
    model: str,
) -> FilterResult:
    inference = llm_gateway.generate(
        "department_matching",
        DepartmentMatchInference,
        model,
        job_title=job_posting.title,
        job_description=job_posting.description,
        department_clusters=_format_department_clusters(department_clusters),
    )

    if inference is None:
        return FilterResult(
            passed=False,
            reason=(
                "Department relevance could not be determined (AI inference unavailable); "
                "excluded by default."
            ),
        )

    passed = inference.confidence >= confidence_threshold
    cluster_description = inference.matched_cluster or "no target department"
    return FilterResult(
        passed=passed,
        reason=f"Matched cluster: {cluster_description}. {inference.reasoning}",
        confidence=inference.confidence,
    )
