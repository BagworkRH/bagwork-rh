#!/usr/bin/env bash
# PostgreSQL backup for bagworkRH — Spec 05 Phase 8 (backups).
#
# Usage:
#   ./scripts/backup_db.sh [--check] [output_dir]   # default: backend/backups
#
#   --check   after dumping, validate the archive with `pg_restore --list`
#             (cheap integrity check; the full drill is scripts/verify_restore.sh)
#
# Reads the same env vars as Django (DB_NAME, DB_USER, DB_PASSWORD, DB_HOST,
# DB_PORT) from `.env` when present. Output is a pg_dump custom-format archive
# ready for `pg_restore`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"

# Load `.env` (same file Django uses) without clobbering real env vars.
if [ -f "${PROJECT_DIR}/.env" ]; then
  set -a
  # shellcheck disable=source
  source "${PROJECT_DIR}/.env"
  set +a
fi

DB_NAME="${DB_NAME:-bagwork_rh}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
CHECK=false
OUT_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK=true ;;
    -*) echo "error: unknown flag $1" >&2; exit 2 ;;
    *) OUT_DIR="$1" ;;
  esac
  shift
done
OUT_DIR="${OUT_DIR:-${PROJECT_DIR}/backups}"

if [ "${DB_ENGINE:-django.db.backends.postgresql}" != "django.db.backends.postgresql" ]; then
  echo "error: DB_ENGINE is not PostgreSQL; backup script is Postgres-only." >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

export PGPASSWORD="${DB_PASSWORD}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${OUT_DIR}/bagwork_rh_${STAMP}.dump"

echo "Backing up '${DB_NAME}'@${DB_HOST}:${DB_PORT} -> ${OUT_FILE}"
pg_dump \
  --host "${DB_HOST}" \
  --port "${DB_PORT}" \
  --username "${DB_USER}" \
  --dbname "${DB_NAME}" \
  --format=custom \
  --file "${OUT_FILE}"

echo "Backup complete: ${OUT_FILE}"

if [ "${CHECK}" = true ]; then
  pg_restore --list "${OUT_FILE}" >/dev/null
  echo "Archive verified readable (pg_restore --list)."
  echo "For a full restore drill: scripts/verify_restore.sh ${OUT_FILE}"
fi

echo "Keep a copy off-machine (managed Postgres usually already snapshots)."