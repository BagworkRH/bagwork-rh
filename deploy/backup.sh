#!/usr/bin/env bash
# Nightly database backup for the compose deployment.
#
#   bash deploy/backup.sh [days_to_keep]      # default: 14
#
# backend/scripts/backup_db.sh assumes a PostgreSQL server on the host and a
# pg_dump binary to match it. Here the server lives in the `db` container, so
# both the dump and its verification run inside that container instead — which
# also guarantees the client version always matches the server.
set -euo pipefail

cd "$(dirname "$0")"

[ -f .env ] || { echo ".env not found" >&2; exit 1; }

DB_NAME="$(grep -E '^DB_NAME=' .env | cut -d= -f2- | tr -d '\r')"
DB_USER="$(grep -E '^DB_USER=' .env | cut -d= -f2- | tr -d '\r')"
KEEP="${1:-14}"

OUT_DIR="backups"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${OUT_DIR}/bagworkrh_${STAMP}.dump"

COMPOSE="docker compose --env-file .env"
mkdir -p "$OUT_DIR"

echo "==> dumping ${DB_NAME} (keeping ${KEEP} days)"
# -T because cron has no TTY; -Fc so the archive is restorable table-by-table
# rather than only as a whole.
$COMPOSE exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$OUT_FILE"

echo "==> verifying the archive is readable"
# No `-` argument: unlike psql, pg_restore does not accept `-` for stdin — it
# reads standard input only when the archive argument is omitted entirely.
# Passing `-` made this line fail with "could not open input file", so every
# backup reported a verification error it had not actually found.
$COMPOSE exec -T db pg_restore --list < "$OUT_FILE" > /dev/null
echo "    ok: $(du -h "$OUT_FILE" | cut -f1)"

echo "==> pruning backups older than ${KEEP} days"
find "$OUT_DIR" -name 'bagworkrh_*.dump' -mtime "+${KEEP}" -print -delete

cat <<'EOF'

Off-machine is the part that actually saves you. A dump on the same disk as the
database does not survive the disk, so sync this directory somewhere else, e.g.
rclone to object storage:

  rclone sync deploy/backups remote:bagworkrh-backups

and prove a restore, because an untested backup is a hope rather than a backup.
The full drill lives in backend/scripts/verify_restore.sh; in this topology run
it against a throwaway database on a scratch machine rather than this one.
EOF
