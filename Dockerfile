# Faz 10 / M10.1: `app` servisi icin tamamlanmis imaj (TDD Section 27
# "Iki konteyner: app (Python sureci - scheduler dongusu + CLI) ve db").
#
# NOT (Chromium): `perform_interactive_login()` (M3.1) `headless=False`
# ile calisir - GORUNUR bir tarayici gerektirir, bu yuzden bu konteynerin
# ICINDE calistirilamaz. M10.1'in kendi "Tamamlanma Dogrulamasi" metni bunu
# ACIKCA istisna tutar ("M3.1'deki tek seferlik LinkedIn girisi disinda
# manuel mudahale olmadan") - bu adim host makinede BIR KEZ calistirilir,
# urettigi oturum durumu SecretsProvider araciligiyla kalici hale getirilir
# (bkz. session_manager.py). Zamanlanmis calistirmalarin KENDISI
# (check_session_is_valid/fetch_search_results_page, ikisi de headless=True)
# bu konteynerin ICINDE calisir - bu yuzden Chromium ve isletim sistemi
# bagimliliklari asagida kurulur.

FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir . \
    && playwright install --with-deps chromium

# `main.py` (Roadmap M10.1): uzun-omurlu scheduler dongusu - varsayilan
# komut. Ayni imaj, tek seferlik/manuel komutlar icin de kullanilir (orn.
# `docker compose run --rm app linkedinbot seed`) - `linkedinbot` konsol
# script'i (pyproject.toml `[project.scripts]`) `pip install .` ile PATH'e
# zaten eklenir.
CMD ["python", "-m", "linkedinbot.main"]
