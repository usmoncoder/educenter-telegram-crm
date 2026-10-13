#!/usr/bin/env bash
# Restore a backup created by backup.sh into the running `db` service.
# Usage: ./scripts/restore.sh backups/educenter-20261012-031500.sql.gz
# WARNING: replaces all current CRM data. The API and worker are stopped during the restore.
set -euo pipefail
cd "$(dirname "$0")/.."
file="${1:-}"
if [[ -z "$file" || ! -f "$file" ]]; then
  echo "Foydalanish: $0 backups/educenter-YYYYmmdd-HHMMSS.sql.gz" >&2
  exit 1
fi
read -r -p "Joriy ma'lumotlar o'chiriladi va $file tiklanadi. Davom etilsinmi? (ha/yo'q) " answer
[[ "$answer" == "ha" ]] || { echo "Bekor qilindi."; exit 1; }
docker compose stop api worker
docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"'
gunzip -c "$file" | docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose run --rm migrate
docker compose start api worker
echo "Tiklash yakunlandi."
