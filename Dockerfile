# Taslak (draft) - bu asama (M0.2) itibariyle henuz kullanilmiyor.
#
# Uygulama konteyneri (`app` servisi), docker-compose.yml'e Faz 10 / M10.1'de
# eklenip bu Dockerfile'a baglanacaktir (bkz. LinkedInBot-Roadmap.md,
# LinkedInBot-TDD.md Section 27 "Dagitim Mimarisi"). Su an itibariyle
# src/linkedinbot'un calisma zamani bagimliligi yoktur (bkz. pyproject.toml)
# ve bir surec giris noktasi (main.py) henuz mevcut degildir; bu yuzden
# burada bir CMD/ENTRYPOINT tanimlanmamistir.

FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir .
