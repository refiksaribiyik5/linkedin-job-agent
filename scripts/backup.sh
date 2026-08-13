#!/usr/bin/env bash
# LinkedInBot - Postgres yedekleme script'i (Roadmap M10.1, TDD Section 27).
#
# TDD Section 27: "Iki konteyner: app... ve db" - bu KASITLI OLARAK ucuncu
# bir uzun-omurlu servis/konteyner (orn. bir cron sidecar) EKLEMEZ. Bunun
# yerine, host'un KENDI zamanlayicisi (orn. `crontab -e` ile eklenen gunluk
# bir satir - TDD'nin KENDI "orn. gunluk cron gorevi" onerisi) bu script'i
# cagirir; script `docker compose exec` araciligiyla `db` konteynerinin
# ICINDEKI `pg_dump`'i kullanir (ayri bir istemci kurulumu host'ta GEREKMEZ).
#
# Kullanim (host'ta, repo kok dizininden):
#   ./scripts/backup.sh
#
# Ornek crontab girdisi (her gun 03:00'te):
#   0 3 * * * cd /path/to/linkedin-job-agent && ./scripts/backup.sh >> backups/backup.log 2>&1
#
# Geri yukleme (restore):
#   gunzip -c backups/linkedinbot-<TIMESTAMP>.sql.gz | docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB"
#
# PRD NFR-11 (asla silme) ve TDD RISK-7 (Single Point of Failure)
# gerekcesiyle eklendi (bkz. LinkedInBot-Roadmap.md M10.1).

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

BACKUP_DIR="${BACKUP_DIR:-backups}"
mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="$BACKUP_DIR/linkedinbot-${TIMESTAMP}.sql.gz"
# `pg_dump | gzip > "$BACKUP_FILE"` dogrudan hedefe yazsaydi, `pg_dump`
# ORTASINDA basarisiz olursa (orn. baglanti kopmasi) YARIM/BOZUK bir
# ".sql.gz" dosyasi, BASARILI bir yedekle AYNI adlandirma semasinda geride
# kalirdi - `set -e`/`pipefail` script'i durdurur ama dosya ZATEN
# olusturulmustur (bagimsiz incelemede bulunan bir bulgu). Bunun yerine
# `local_keyring_adapter.py::_write_all()` ile AYNI desen: gecici bir
# dosyaya yaz, yalnizca BASARIYLA tamamlaninca hedefe TASI (atomik).
TMP_FILE="${BACKUP_FILE}.tmp"
trap 'rm -f "$TMP_FILE"' EXIT

POSTGRES_USER="${POSTGRES_USER:-linkedinbot}"
POSTGRES_DB="${POSTGRES_DB:-linkedinbot}"

docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$TMP_FILE"
mv "$TMP_FILE" "$BACKUP_FILE"
trap - EXIT

echo "Yedek olusturuldu: $BACKUP_FILE"
