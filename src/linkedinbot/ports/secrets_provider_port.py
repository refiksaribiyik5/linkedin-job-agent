"""SecretsProviderPort - secrets erisimi icin soyut arayuz (Roadmap M2.3,
TDD Section 24).

TDD Section 24 "Erisim kurali": "Hicbir modul SecretsProvider'i bypass edip
secrets'a dogrudan dosya/env okuyarak erisemez; tum erisim
`secrets_provider_port.get(key)` uzerinden gecer." Bu Port, o kuralin
somut, kod-seviyesi karsiligidir - V1'de yalnizca iki secret sinifi vardir
(LLM saglayici API anahtari, LinkedIn oturum durumu - bkz. TDD Section 24
"Kapsam"), ama Port bu ikisine ozel degildir; herhangi bir anahtar/deger
cifti icin genel bir depodur.

`delete()` gibi bir metod kasitli olarak eklenmez - ne PRD ne de TDD
boyle bir islemden bahseder; eklemek, bu milestone'un kapsaminda olmayan
bir davranis icat etmek olurdu.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class SecretsProviderPort(ABC):
    """Anahtar/deger tabanli bir secrets deposu icin temel islemler."""

    @abstractmethod
    def get(self, key: str) -> str | None:
        """Secret bulunamazsa None doner (sessizce bir varsayilan
        uretmez - cagiran, eksik bir secret'i nasil ele alacagina kendisi
        karar verir)."""

    @abstractmethod
    def set(self, key: str, value: str) -> None:
        """Var olan bir degeri sessizce uzerine yazar (ayri bir "guncelle"
        metodu yoktur - TDD/PRD boyle bir ayrim tanimlamaz)."""
