"""Department Filter icin CANLI entegrasyon testi (Roadmap M6.4).

Roadmap M6.4 "Tamamlanma Dogrulamasi": "15-20 baslik/aciklama ciftinden
olusan kuratorlu bir test seti (tam eslesme, yakin-anlamsal eslesme, acik
eslesmeme, her iki dilde) manuel olarak beklenen sonuclarla
karsilastirilir." Bu, GERCEK bir semantik degerlendirme gerektirir -
`tests/unit/filtering/test_department_filter.py`'nin sahte (mock)
Gateway'i bu kriteri KARSILAYAMAZ (biz ne donecegini kendimiz
belirliyoruz, LLM'in gercek anlama yetenegini olcmuyoruz).

`ANTHROPIC_API_KEY` ortam degiskeni ayarlanmamissa bu test ATLANIR - M5.1'in
`test_anthropic_adapter_live.py`'siyle AYNI, acikca belgelenmis sinirlama
(bu ortamda gercek bir Anthropic API anahtari yoktur). Gercek bir
anahtarla calistirilip calistirilmadigini projenin sahibi dogrulamalidir.

Beklenti tam bir sayisal esik degil, DOGRU YONDE bir sinif ayrimidir:
acik eslesmeyen ciftler icin confidence < esik, tam/yakin-anlamsal
eslesen ciftler icin confidence >= esik. Curated set PRD Section 11.2'nin
kendi alti kumesinden VE kendi ornek unvanlarindan (Ticaret Uzman
Yardimcisi, BD Associate) alinmistir.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from linkedinbot.adapters.llm.anthropic_adapter import AnthropicLLMAdapter
from linkedinbot.adapters.llm.gateway import LLMGateway
from linkedinbot.adapters.llm.prompt_registry import PromptRegistry
from linkedinbot.domain.job_posting import JobPosting
from linkedinbot.filtering.department_filter import filter_by_department

_REPO_ROOT = Path(__file__).resolve().parents[3]

_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
_TEST_MODEL = "claude-3-5-haiku-20241022"
_CONFIDENCE_THRESHOLD = 0.65

pytestmark = pytest.mark.skipif(
    not _API_KEY,
    reason="ANTHROPIC_API_KEY ayarlanmamis - gercek Anthropic API cagrisi atlanir.",
)

# PRD Section 11.2'nin kendi alti kumesi + orada listelenen ornek unvanlar.
_DEPARTMENT_CLUSTERS = {
    "Sales & Business Development": [
        "Sales",
        "Sales Executive",
        "Key Account",
        "Account Management",
        "Business Development",
        "Business Development Executive",
        "Business Development Specialist",
    ],
    "Strategy & Growth": [
        "Strategy",
        "Strategic Planning",
        "Corporate Strategy",
        "Growth",
        "Growth Strategy",
        "Strategy & Business Development",
    ],
    "Marketing": ["Marketing", "Digital Marketing", "Brand Marketing", "Product Marketing"],
    "Trade, Logistics & Supply Chain": [
        "Trade",
        "International Trade",
        "Foreign Trade",
        "Export",
        "Import",
        "Logistics",
        "Supply Chain",
    ],
    "Commercial": ["Commercial", "Commercial Excellence"],
    "Consulting": ["Consulting", "Management Consulting", "Business Consulting"],
}

COLLECTED_AT = "2026-08-09T12:00:00+00:00"

# (baslik, aciklama, beklenen: True=esik uzerinde geciyor, False=esik altinda kaliyor)
_CURATED_CASES = [
    # --- Tam eslesme (EN) ---
    ("Sales Executive", "Manage a portfolio of key accounts in Istanbul.", True),
    ("Digital Marketing Specialist", "Run paid social and SEO campaigns.", True),
    ("Supply Chain Analyst", "Coordinate import/export logistics.", True),
    ("Management Consultant", "Advise clients on operational strategy.", True),
    # --- Tam eslesme (TR) ---
    ("Satış Uzmanı", "Anahtar müşteri portföyünü yönetir.", True),
    ("Dış Ticaret Uzmanı", "İhracat ve ithalat operasyonlarını yürütür.", True),
    # --- Yakin-anlamsal eslesme (EN) - PRD 11.2'nin kendi ornegi ---
    ("BD Associate", "Support new business development efforts across sectors.", True),
    ("Growth Lead", "Own the company's growth strategy and experiments.", True),
    ("Trade Compliance Officer", "Manage customs documentation for cross-border trade.", True),
    # --- Yakin-anlamsal eslesme (TR) - PRD 11.2'nin kendi ornegi ---
    ("Ticaret Uzman Yardımcısı", "Uluslararası ticaret operasyonlarına destek verir.", True),
    ("Büyüme Stratejisi Uzmanı", "Şirketin büyüme stratejisini yönetir.", True),
    # --- Acik eslesmeme (EN) ---
    ("Software Engineer", "Build backend services in Python.", False),
    ("Warehouse Forklift Operator", "Operate a forklift in a distribution center.", False),
    ("Registered Nurse", "Provide patient care in a hospital ward.", False),
    # --- Acik eslesmeme (TR) ---
    ("Yazılım Mühendisi", "Python ile backend servisleri geliştirir.", False),
    ("Hemşire", "Hastane servisinde hasta bakımı sağlar.", False),
]


def _job_posting(title: str, description: str) -> JobPosting:
    return JobPosting(
        job_id=f"https://www.linkedin.com/jobs/view/{hash(title) & 0xFFFFFF}",
        title=title,
        company_id="Acme Corp",
        location="Istanbul, Turkey",
        posted_date=COLLECTED_AT,
        description=description,
        application_url=f"https://www.linkedin.com/jobs/view/{hash(title) & 0xFFFFFF}",
        collected_at=COLLECTED_AT,
    )


@pytest.mark.parametrize(("title", "description", "expected_passes"), _CURATED_CASES)
def test_department_filter_classifies_curated_title_description_pairs_correctly(
    title, description, expected_passes
):
    llm_gateway = LLMGateway(
        llm_provider=AnthropicLLMAdapter(api_key=_API_KEY),
        prompt_registry=PromptRegistry(prompts_dir=_REPO_ROOT / "config" / "prompts"),
    )
    job_posting = _job_posting(title, description)

    result = filter_by_department(
        job_posting, _DEPARTMENT_CLUSTERS, _CONFIDENCE_THRESHOLD, llm_gateway, _TEST_MODEL
    )

    assert result.passed is expected_passes, (
        f"title={title!r} description={description!r} "
        f"expected passed={expected_passes} but got {result.passed} "
        f"(confidence={result.confidence}, reason={result.reason!r})"
    )
