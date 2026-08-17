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

# Persistent Chromium profili + noVNC altyapisi (Commit 1 - gercek kullanim
# Commit 2'nin `linkedinbot login` komutuyla baslar): bu paketler ana
# surecin (main.py) CALISMASI icin GEREKLI DEGILDIR, yalnizca INSAN-tetikli
# interaktif login sirasinda kullanilir (bkz. entrypoint.sh'in kendi
# dokumani).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        xvfb \
        x11vnc \
        novnc \
        websockify \
    && rm -rf /var/lib/apt/lists/*

# Xvfb'nin sanal ekran numarasi - image-SEVIYESINDE (ENV, runtime `export`
# DEGIL) tanimlanir ki hem entrypoint.sh'in baslattigi Xvfb hem de SONRADAN
# `docker compose exec` ile calistirilacak ayri bir process (Commit 2'nin
# `linkedinbot login` komutu) AYNI degeri otomatik gorsun - `docker exec`
# yalnizca image/compose seviyesinde tanimli ortam degiskenlerini miras
# alir, bir shell script icinde runtime'da `export` edilmis degiskenleri
# DEGIL.
ENV DISPLAY=:99

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]

# `main.py` (Roadmap M10.1): uzun-omurlu scheduler dongusu - varsayilan
# komut. Ayni imaj, tek seferlik/manuel komutlar icin de kullanilir (orn.
# `docker compose run --rm app linkedinbot seed`) - `linkedinbot` konsol
# script'i (pyproject.toml `[project.scripts]`) `pip install .` ile PATH'e
# zaten eklenir. ENTRYPOINT (yukarida) bu komutu CALISTIRAN sey DEGIL, ONA
# giden bir on-adimdir (Xvfb/x11vnc/noVNC arka plana alinir, SONRA `exec
# "$@"` ile bu CMD/override edilen komut PID 1 olarak devralir) - bkz.
# entrypoint.sh.
CMD ["python", "-m", "linkedinbot.main"]
