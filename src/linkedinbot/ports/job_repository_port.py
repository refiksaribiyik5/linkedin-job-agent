"""JobRepositoryPort - job_postings tablosu icin soyut arayuz.

job_postings bir Shared/Reference tablodur (PRD Section 15.0, TDD Section
14): gercek dunyadaki ilana aittir, bir hesaba degil. Bu yuzden bu Port'un
hicbir metodu account_id parametresi almaz - AccountRepositoryPort'un
aksine, burada account_id'nin YOKLUGU da TDD Section 14'un dogrudan bir
gereksinimidir.

`content_hash` neden `JobPosting` domain modeline eklenmedi (istisnai bir
karar, gerekcesiyle): domain/job_posting.py'nin kendi modul dokumani
(M1.1, zaten onaylanmis) content_hash hesaplamasini acikca ve kasitli
olarak M4.1'in (Normalization Service) sorumluluguna birakir - "toplama
... normalizasyon (content hash) ... sonraki milestone'ların işidir".
`content_hash`, FR-14 geregi yalnizca Title/Experience Level/Location/
Workplace Type/Description alanlarindan hesaplanir; ancak "Experience
Level" M1.1'de JobPosting'in bir alani bile degildir (M6.3'te ayrica
cikarilir) - yani hash algoritmasi henuz tanimlanabilir durumda degildir.
Bu, EvaluatedJob/Report'taki eksik alanlardan (gozden kacmis, is anlami
zaten mevcut) farkli bir durumdur: burada alan bilerek ve gerekcelendirerek
baska bir milestone'a birakilmistir. Bu yuzden `content_hash` domain
modeline zorla eklenmez; bunun yerine create/update metodlarina, cagiranin
(M4.1'in Normalization Service'i) zaten hesaplamis olacagi degeri actikca
gecmesini saglayan ayri bir parametre olarak eklenir.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from linkedinbot.domain.job_posting import JobPosting


class JobRepositoryPort(ABC):
    """job_postings tablosu icin temel create/read/update islemleri (Roadmap M1.3)."""

    @abstractmethod
    def create(self, job_posting: JobPosting, content_hash: str) -> JobPosting:
        """Yeni bir ilan satiri olusturur."""

    @abstractmethod
    def get_by_id(self, job_id: str) -> JobPosting | None:
        """Ilan bulunamazsa None doner."""

    @abstractmethod
    def update(self, job_posting: JobPosting, content_hash: str) -> JobPosting:
        """Var olan bir ilan satirini gunceller (orn. FR-14 anlamli degisiklik)."""
