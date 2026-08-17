#!/bin/sh
# entrypoint.sh - `app` konteynerinin giris scripti (persistent Chromium
# profili + noVNC altyapisi hazirligi - Commit 1; gercek kullanim Commit 2'de
# eklenecek `linkedinbot login` komutuyla baslar).
#
# NEDEN bir supervisor (supervisord vb.) DEGIL: Xvfb/x11vnc/noVNC, ana Python
# surecinin (main.py, APScheduler dongusu) CALISMASI icin GEREKLI DEGILDIR -
# yalnizca INSAN-tetikli interaktif login sirasinda kullanilir; main.py
# bunlarsiz da tam calisir. Bu yuzden bir process manager'in bunlari
# "izleyip yeniden baslatmasi" GEREKMEZ - cokmus/kapali kalmis olsalar bile
# ana surecin restart-resilience (M11.5) beklentisiyle kesintisiz calismaya
# devam etmesi gerekir; bir supervisor eklemek bu garantiyi GEREKSIZ YERE
# baska bir process manager'in KENDI saglik/restart mantigina baglardi.
# Basit bir "arka planda baslat, unut" (fire-and-forget) yeterlidir - bir
# sonraki interaktif login denemesi (nadiren, insan gozetiminde) bu
# servislerin ayakta olup olmadigini zaten DOGAL olarak fark eder (noVNC
# baglanamazsa insan hemen gorur).
#
# `exec "$@"` (script'in EN SONU): ana Python sureci (CMD, varsayilan
# "python -m linkedinbot.main"; `docker compose run --rm app linkedinbot
# ...` gibi override edilmis komutlar da BURAYA "$@" olarak gelir) bu
# shell'in YERINE gecer (PID 1 olur) - boylece `docker compose stop`/
# SIGTERM/`restart: unless-stopped` davranisi BUGUNKUYLE TAMAMEN AYNI kalir
# (main.py'nin kendi `register_signal_handlers` mekanizmasi degismeden
# calisir). Xvfb/x11vnc/noVNC bu satirdan ONCE arka plana (&) alinip
# "unutulur" - onlarin PID 1 olmasi/kalmasi hic gerekmez.
set -e

: "${DISPLAY:=:99}"
: "${BROWSER_PROFILE_DIR:=/app/browser-profile}"

# Kalici profil dizini - Commit 2'de gercek Chromium profili buraya
# yazilacak; bu commit'te YALNIZCA dizinin VAR OLDUGUNU ve izinlerinin
# (0700 - secrets/ dizini icin TDD Section 24'un ZATEN uyguladigi ayni
# disiplin, cunku bu dizin de authentication state tasiyacak) dogru
# oldugunu garanti eder. Var olan icerige DOKUNMAZ (yalnizca mkdir -p +
# chmod, idempotent).
mkdir -p "$BROWSER_PROFILE_DIR"
chmod 700 "$BROWSER_PROFILE_DIR"

Xvfb "$DISPLAY" -screen 0 1280x800x24 -nolisten tcp >/var/log/xvfb.log 2>&1 &

# Xvfb'nin X soketi hazir olana kadar kisa bir bekleme - x11vnc, Xvfb HENUZ
# dinlemeye baslamadan baglanmaya calisirsa hata verip cikar.
_display_num=${DISPLAY#:}
_i=0
while [ "$_i" -lt 20 ]; do
    [ -e "/tmp/.X11-unix/X${_display_num}" ] && break
    _i=$((_i + 1))
    sleep 0.25
done

if [ -n "$VNC_PASSWORD" ]; then
    x11vnc -display "$DISPLAY" -forever -shared -rfbport 5900 \
        -passwd "$VNC_PASSWORD" -quiet >/var/log/x11vnc.log 2>&1 &
    websockify --web=/usr/share/novnc/ 6080 localhost:5900 \
        >/var/log/novnc.log 2>&1 &
else
    # VNC_PASSWORD BOSSA x11vnc/noVNC KASITLI OLARAK HIC BASLATILMAZ -
    # parolasiz bir VNC sunucusunu (LinkedIn kimlik bilgilerinin gorunecegi
    # bir ekrani) ACIK BIRAKMAK yerine, M11.3'un "fail loudly, never
    # silently" ilkesiyle tutarli sekilde net bir uyari yazilir; main.py
    # buna bagimli OLMADIGI icin surec normal devam eder.
    echo "UYARI: VNC_PASSWORD ayarlanmamis - x11vnc/noVNC baslatilmadi. Interaktif login icin .env'de VNC_PASSWORD ayarlayip container'i yeniden baslatin." >&2
fi

exec "$@"
