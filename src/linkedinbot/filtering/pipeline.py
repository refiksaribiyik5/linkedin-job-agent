"""Filtreleme Zinciri Montaji - Blacklist -> Location -> Experience ->
Department (Roadmap M6.5, TDD Section 11.4).

**Sira ve kisa devre:** TDD Section 11.4'un maliyet-sirali filtreleme
ilkesi ("AI cagrisini en son, en ucuz filtrelerden sonra calistir") geregi,
zincir M6.1-M6.4'u AYNEN, degistirmeden, bu sirayla cagirir VE bir asama
reddederse (`passed=False`) SONRAKI asamalar o ilan icin HIC
CAGRILMAZ - erken reddedilen bir ilan icin (orn. Blacklist'te elenen)
Deneyim/Departman'in LLM maliyetine hic girilmez.

**`FilterResultDetail` (TDD Section 6/Roadmap M6.5'te adi gecen ama hicbir
yerde semasi verilmeyen kavram):** `EvaluatedJob.filter_result_detail:
dict[str, FilterResult] | None` (M1.1, degistirilmemis) zaten bu kavramin
somut seklini verir - filtre adindan (`"blacklist"`, `"location"`,
`"experience"`, `"department"`) o filtrenin `FilterResult`'ina bir dict.
Bu modul bu sekli birebir kullanir; yalnizca FIILEN CALISTIRILAN
filtrelerin sonucu dict'e eklenir (kisa devre nedeniyle erken durursa
sonraki anahtarlar hic YOKTUR - "sessizce bos/varsayilan" DEGIL, basitce
"o asamaya hic ulasilmadi").

**Borderline (proje talimatiyla acikca onaylanan mimari karar,
kullanicinin M6.5 durdurma-ve-karar surecinde verdigi ACIK KARAR):** TDD
Section 11.4, uc-degerli (passed/rejected/borderline) ciktiyi ACIKCA
`Filtering Pipeline` (bu modul) seviyesine atfeder - tek bir filtre
fonksiyonuna degil (bkz. M6.1-M6.4'un HICBIRINDE borderline mantigi
YOKTUR - kasitli olarak). Yalnizca Department, "config'teki dept
confidence threshold ± bir tolerans" ile borderline uretebilir; ancak PRD
Section 17'nin konfigurasyon tablosunda Department'a ozel boyle bir
tolerans parametresi TANIMLI DEGILDIR (yalnizca 0-100 puanlik AI Match
Score olceginde tanimli "Borderline Bant Genisligi" vardir, 0.0-1.0
olcekli Department guvenine dogrudan uygulanamaz). Kullanici acikca
Secenek A'yi onayladi: `department_confidence_tolerance: float`,
`confidence_threshold` (M6.4) ile AYNI desende, dogrudan cagirana
birakilan duz bir parametredir - HICBIR YERDE (bu modul, config, veya
baska bir varsayilan) sabit-kodlanmaz.

`PipelineResult.passed`/`is_borderline` ayrimi, `EvaluatedJob`'un (M1.1)
zaten kurdugu "borderline, durum enum'unun bir kolu degil, ayri bir
boolean bayraktir" desenini birebir izler (bkz. domain/evaluated_job.py
modul dokumani): borderline bir ilan `passed=True` (TDD'nin "ilan yine de
bir sonraki asamaya... ilerler" ifadesiyle tutarli - ilan pipeline'da
DEVAM EDER) VE `is_borderline=True` olarak isaretlenir - bu iki alan
birbirinden BAGIMSIZDIR, uc-degerli bir enum yerine.

**Department'in "kesin red" vs "borderline" ayrimi:** Department
`passed=False` dondugunde (confidence < esik), guven skoru
`[esik - tolerans, esik)` araligindaysa borderline (`passed=True,
is_borderline=True`); bu araligin ALTINDAYSA kesin red
(`passed=False, is_borderline=False`). Department'in kendi Gateway
basarisizligi durumunda (confidence=None, bkz. department_filter.py) bu
karsilastirma yapilamaz - dogrudan kesin red olarak ele alinir (bir
sayi UYDURULMAZ).
"""

from __future__ import annotations

from pydantic import BaseModel

from linkedinbot.adapters.llm.gateway import LLMGateway
from linkedinbot.domain.evaluated_job import FilterResult
from linkedinbot.domain.job_posting import JobPosting
from linkedinbot.domain.user_profile import Preferences
from linkedinbot.filtering.blacklist_filter import filter_by_blacklist
from linkedinbot.filtering.department_filter import filter_by_department
from linkedinbot.filtering.experience_filter import filter_by_experience_level
from linkedinbot.filtering.location_filter import filter_by_location


class PipelineResult(BaseModel):
    passed: bool
    is_borderline: bool = False
    filter_result_detail: dict[str, FilterResult]


def _run_pipeline_for_one_job(
    job_posting: JobPosting,
    preferences: Preferences,
    target_locations: list[str],
    accepted_experience_levels: list[str],
    department_clusters: dict[str, list[str]],
    department_confidence_threshold: float,
    department_confidence_tolerance: float,
    llm_gateway: LLMGateway,
    model: str,
) -> PipelineResult:
    detail: dict[str, FilterResult] = {}

    blacklist_result = filter_by_blacklist(job_posting, preferences)
    detail["blacklist"] = blacklist_result
    if not blacklist_result.passed:
        return PipelineResult(passed=False, filter_result_detail=detail)

    location_result = filter_by_location(job_posting, target_locations)
    detail["location"] = location_result
    if not location_result.passed:
        return PipelineResult(passed=False, filter_result_detail=detail)

    experience_result = filter_by_experience_level(
        job_posting, accepted_experience_levels, llm_gateway, model
    )
    detail["experience"] = experience_result
    if not experience_result.passed:
        return PipelineResult(passed=False, filter_result_detail=detail)

    department_result = filter_by_department(
        job_posting, department_clusters, department_confidence_threshold, llm_gateway, model
    )
    detail["department"] = department_result
    if department_result.passed:
        return PipelineResult(passed=True, filter_result_detail=detail)

    confidence = department_result.confidence
    if confidence is not None and confidence >= (
        department_confidence_threshold - department_confidence_tolerance
    ):
        return PipelineResult(passed=True, is_borderline=True, filter_result_detail=detail)

    return PipelineResult(passed=False, filter_result_detail=detail)


def run_filtering_pipeline(
    job_postings: list[JobPosting],
    preferences: Preferences,
    target_locations: list[str],
    accepted_experience_levels: list[str],
    department_clusters: dict[str, list[str]],
    department_confidence_threshold: float,
    department_confidence_tolerance: float,
    llm_gateway: LLMGateway,
    model: str,
) -> list[tuple[JobPosting, PipelineResult]]:
    return [
        (
            job_posting,
            _run_pipeline_for_one_job(
                job_posting,
                preferences,
                target_locations,
                accepted_experience_levels,
                department_clusters,
                department_confidence_threshold,
                department_confidence_tolerance,
                llm_gateway,
                model,
            ),
        )
        for job_posting in job_postings
    ]
