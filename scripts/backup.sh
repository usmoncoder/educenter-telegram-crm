#!/usr/bin/env bash
# Create a compressed logical backup of the CRM database.
# Usage: ./scripts/backup.sh            (writes backups/educenter-YYYYmmdd-HHMMSS.sql.gz)
# Schedule it with cron, e.g.:  15 3 * * * cd /opt/educenter-crm && ./scripts/backup.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
chmod 700 backups
stamp=$(date +%Y%m%d-%H%M%S)
out="backups/educenter-${stamp}.sql.gz"
docker compose exec -T db sh -c 'pg_dump --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip -9 > "$out"
chmod 600 "$out"
# Keep the 14 most recent backups.
ls -1t backups/educenter-*.sql.gz | tail -n +15 | xargs -r rm --
echo "Backup yaratildi: $out ($(du -h "$out" | cut -f1))"
