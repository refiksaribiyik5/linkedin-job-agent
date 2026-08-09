"""Experience Level Filter - FR-5, PRD Section 11.3, EDGE-1, EDGE-12
(Roadmap M6.3).

**Kural tabanli + LLM fallback (Roadmap M6.3 "Amac"):** Once ucuz,
deterministik bir kural tabanli kontrol denenir; yalnizca hem baslik HEM
aciklama "unknown" (ne kabul edilen bir seviye adi ne de acik bir kidem
sinyali) donerse LLM Gateway'e (M5.3) dusulur - Section 11.4'un "AI
cagrisini en son, en ucuz filtrelerden sonra calistir" ilkesiyle
tutarlidir.

**Kural tabanli sinyal seti:** PRD 11.3'un kendi ornekleri ("3+ years",
"Manager", "Team Lead" - "Management Trainee" istisnasi haric) VE
M5.2'nin zaten onaylanmis `config/prompts/experience_inference.prompt.md`
sablonunun ayni ornekleri birebir kullanilir - baska bir anahtar kelime
ICAT EDILMEMISTIR (orn. "Senior" gibi ek bir terim bilincli olarak
eklenmemistir; boyle bir baslik kural tabanli asamada "unknown" kalir ve
LLM'e duser, ki LLM zaten ayni sablonun talimatlarina gore dogru sekilde
degerlendirir).

**EDGE-12 (celiski onceligi):** Baslik ve aciklama BAGIMSIZ olarak
degerlendirilir; aciklamanin sinyali "unknown" DEGILSE her zaman
kullanilir (celiskili olsun ya da olmasin) - yalnizca aciklama "unknown"
oldugunda basligin sinyaline basvurulur. Bu, FR-5'in "aciklama metnindeki
sinyal onceliklidir" kuralinin dogal bir genellemesidir.

**"Management Trainee" istisnasi KUresel'dir:** Baslik VEYA aciklamadan
HERHANGI biri "Management Trainee"/"MT Program" iceriyorsa, disqualifying
kontrol HER IKI metin icin de devre disi birakilir - aksi halde bir
trainee programinin aciklamasinda gecen sonradan gelen bir "manager"
sozcugu (orn. "resmi bir Manager'a raporlarsiniz"), programin kendisi
acikca "Management Trainee" olarak etiketlenmis olsa bile, o metni
yanlislikla disqualifying olarak isaretlerdi.

**TDD Section 11.4'un acik ifadesi geregi (proje talimatiyla acikca
onaylanan mimari karar):** Filtreleme asamasi Location/Experience/
Blacklist icin KESIN `passed`/`rejected` doner; "borderline" yalnizca
Department icindir (Department guven skoru esige yakinsa) - PRD
EDGE-1'in "borderline bucket" ifadesi, TDD'nin bu daha ozgul, gerekceli
mimari cozumu tarafindan GECERSIZ KILINIR (M2.1'in `config/schema.py`
modul dokumaninda zaten kurulmus olan "TDD'nin daha ozgul cozumu, PRD/
Roadmap'in daha genel ifadesinin onune gecer" desenininin AYNISI). Bu
yuzden `confidence` alani her zaman `None` birakilir ve LLM'in kendi
yanitindan (`ExperienceLevelInference`) SAYISAL bir guven skoru talep
edilmez - PRD Section 17'nin konfigurasyon tablosunda deneyim icin
herhangi bir esik/guven parametresi de zaten YOKTUR (yalnizca Department
Match Confidence Esigi - 0.65 - tanimlidir).

**LLM cagrisi basarisiz olursa (Gateway None doner - M5.3'un "repair"
girisimi de basarisiz oldu):** M5.3'un "asla uydurma bir skor uretme"
ilkesiyle tutarli olarak, bu durum sessizce kabul olarak YORUMLANMAZ;
EDGE-3'un (Location, M6.2) "varsayilan olarak dislanir ama nedeni acikca
belirtilir" ile ayni tutarli, muhafazakar varsayilanla REDDEDILIR - bir
skor/karar UYDURULMAZ.

**TDD Section 6'nin modul bagimlilik tablosuyla gorunur celiski:** O
tablo "filtering | ... | llm_provider_port (yalnizca Department
filtresi)" der - ama Roadmap M6.3'un kendi "Bagimliliklar: M6.2, **M5.3**"
satiri VE "Tamamlanma Dogrulamasi"ndaki acik "belirsiz durum -> LLM
yoluna (mock) yonlendirilir" senaryosu, VE PRD EDGE-1'in kendisi
("Icerikten AI cikarimi yapilir") Experience'in de LLM'e ihtiyac
duydugunu ACIKCA belirtir. Roadmap'in bu milestone'a ozel, ayrintili
bolumu (ve onu dogrulayan PRD EDGE-1) burada esas alinmistir; TDD
Section 6'nin ozet tablosu eksik/sadelestirilmis kabul edilmistir.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from linkedinbot.adapters.llm.gateway import LLMGateway
from linkedinbot.domain.evaluated_job import FilterResult
from linkedinbot.domain.job_posting import JobPosting

_YEARS_PATTERN = re.compile(r"\b\d+\+\s*years?\b", re.IGNORECASE)
_DISQUALIFYING_KEYWORDS = ("manager", "team lead")
_MANAGEMENT_TRAINEE_EXCEPTION_PHRASES = ("management trainee", "mt program")


class ExperienceLevelInference(BaseModel):
    matches_accepted_level: bool
    reasoning: str


def _is_management_trainee_program(job_posting: JobPosting) -> bool:
    combined = f"{job_posting.title} {job_posting.description}".lower()
    return any(phrase in combined for phrase in _MANAGEMENT_TRAINEE_EXCEPTION_PHRASES)


def _has_disqualifying_signal(text: str, *, exempt: bool) -> bool:
    if exempt:
        return False
    text_lower = text.lower()
    if _YEARS_PATTERN.search(text_lower):
        return True
    return any(keyword in text_lower for keyword in _DISQUALIFYING_KEYWORDS)


def _has_accepted_level_signal(text: str, accepted_experience_levels: list[str]) -> bool:
    text_lower = text.lower()
    return any(level.lower() in text_lower for level in accepted_experience_levels)


def _rule_based_signal(
    text: str, accepted_experience_levels: list[str], *, trainee_exempt: bool
) -> bool | None:
    """`True` = kabul, `False` = red, `None` = "unknown" (sinyal yok)."""
    if _has_disqualifying_signal(text, exempt=trainee_exempt):
        return False
    if _has_accepted_level_signal(text, accepted_experience_levels):
        return True
    return None


def filter_by_experience_level(
    job_posting: JobPosting,
    accepted_experience_levels: list[str],
    llm_gateway: LLMGateway,
    model: str,
) -> FilterResult:
    trainee_exempt = _is_management_trainee_program(job_posting)
    title_signal = _rule_based_signal(
        job_posting.title, accepted_experience_levels, trainee_exempt=trainee_exempt
    )
    description_signal = _rule_based_signal(
        job_posting.description, accepted_experience_levels, trainee_exempt=trainee_exempt
    )
    final_signal = description_signal if description_signal is not None else title_signal

    if final_signal is True:
        return FilterResult(
            passed=True,
            reason="Job posting matches an accepted experience level.",
        )
    if final_signal is False:
        return FilterResult(
            passed=False,
            reason="Job posting shows an explicit seniority signal beyond accepted levels.",
        )

    inference = llm_gateway.generate(
        "experience_inference",
        ExperienceLevelInference,
        model,
        job_title=job_posting.title,
        job_description=job_posting.description,
        accepted_experience_levels=", ".join(accepted_experience_levels),
    )

    if inference is None:
        return FilterResult(
            passed=False,
            reason=(
                "Experience level could not be determined (AI inference unavailable); "
                "excluded by default."
            ),
        )

    return FilterResult(
        passed=inference.matches_accepted_level,
        reason=f"AI inference: {inference.reasoning}",
    )
