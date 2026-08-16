#!/usr/bin/env bash
# LinkedInBot - Colima'yi host (macOS) yeniden baslatildiginda otomatik
# baslatan bir LaunchAgent kurar (Roadmap M11.5).
#
# Neden gerekli: `docker-compose.yml`'deki `app` servisinin `restart:
# unless-stopped` politikasi, YALNIZCA Docker daemon'i zaten calisiyorsa
# ise yarar. Colima (Docker daemon'in host'taki VM'i), macOS'un kendisi
# tarafindan otomatik baslatilmaz - bir host yeniden baslatmasi (orn. bir
# guvenlik guncellemesi) sonrasinda Colima calismadigi surece `app`
# konteyneri de HICBIR ZAMAN baslamaz, `restart: unless-stopped`
# politikasi devreye giremeden. Bu script, o bosluğu dolduran tek-seferlik
# host kurulumudur.
#
# Kullanim (host'ta, macOS'ta, bir kez calistirilir - tekrar calistirmak
# guvenlidir/idempotenttir):
#   ./scripts/install_colima_autostart.sh
#
# Kaldirmak icin:
#   launchctl bootout "gui/$(id -u)/com.linkedinbot.colima-autostart"
#   rm ~/Library/LaunchAgents/com.linkedinbot.colima-autostart.plist
#
# TDD Section 9/NFR-2 (gozetimsiz calistirma guvenilirligi) gerekcesiyle
# eklendi (bkz. LinkedInBot-Roadmap.md M11.5). Gercek bir host yeniden
# baslatmasindan sonra `docker ps`'in `app` konteynerini "Up" gosterdigini
# dogrulamak KASITLI olarak bu script'in degil, Roadmap M12'nin (Production
# Verification) isidir.

set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Bu script yalnizca macOS'ta calisir (LaunchAgent, macOS'a ozgu bir mekanizmadir)." >&2
  exit 1
fi

COLIMA_BIN="$(command -v colima || true)"
if [[ -z "$COLIMA_BIN" ]]; then
  echo "colima PATH'te bulunamadi - once colima'yi kurun (orn. 'brew install colima')." >&2
  exit 1
fi
COLIMA_BIN_DIR="$(dirname "$COLIMA_BIN")"

LABEL="com.linkedinbot.colima-autostart"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$HOME/Library/Logs/linkedinbot"
mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

# `ProgramArguments` MUTLAK bir yol gerektirir - launchd, kullanicinin
# kabuk $PATH'ini miras ALMAZ; bu yuzden `colima`'nin yolu burada, kurulum
# ANINDA (calisma zamaninda degil) COZULUP plist'e SABIT olarak yazilir.
# `EnvironmentVariables`/`PATH` de AYNI gerekceyle GEREKLIDIR (canli olarak
# dogrulanan bir bulgu): `colima start`'in KENDISI, ic'te `limactl`/`docker`
# gibi baska Homebrew ikili dosyalarini KENDI PATH'inden cozer - launchd'nin
# minimal varsayilan PATH'i (`/usr/bin:/bin:/usr/sbin:/sbin`) bunlari
# icermez, bu yuzden `colima start` launchd altinda "limactl: executable
# file not found" ile basarisiz olurdu (COLIMA_BIN'in kendisi mutlak bir
# yol olsa bile).
cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${COLIMA_BIN}</string>
        <string>start</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${COLIMA_BIN_DIR}:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/colima-autostart.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/colima-autostart.log</string>
</dict>
</plist>
PLIST

# Idempotentlik: onceden yuklenmis olabilecek bir kopya once kaldirilir -
# ILK kurulumda "zaten yuklu degil" hatasi BEKLENIR/zararsizdir (bu yuzden
# `|| true`), boylece script HER ZAMAN guvenle tekrar calistirilabilir.
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"

echo "LaunchAgent kuruldu ve yuklendi: $PLIST_PATH"
echo "Colima artik host girisinde (ve bu script'in her calistirilmasinda) otomatik baslatilacak."
echo "Loglar: ${LOG_DIR}/colima-autostart.log"
