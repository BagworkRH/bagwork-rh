#!/usr/bin/env bash
# PostgreSQL restore for bagworkRH — Spec 05 Phase 8 (recovery).
#
# Usage:
#   ./scripts/restore_db.sh /path/to/bagwork_rh_YYYYMMDD_HHMMSS.dump
#
# WARNING: this DROPS and recreates the target database contents. Run against
# a disposable/staging database first and always verify the latest backup
# works (tested restores) before relying on it in an incident.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"

if [ $# -lt 1 ]; then
  echo "usage: $0 <backup.dump>" >&2
  exit 1
fi
BACKUP_FILE="$(realpath "$1")"
[ -f "${BACKUP_FILE}" ] || { echo "error: ${BACKUP_FILE} not found" >&2; exit 1; }

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

export PGPASSWORD="${DB_PASSWORD}"

echo "Restoring '${BACKUP_FILE}' into '${DB_NAME}'@${DB_HOST}:${DB_PORT}"
echo "-> Dropping and recreating databases may take a moment..."
pg_restore \
  --host "${DB_HOST}" \
  --port "${DB_PORT}" \
  --username "${DB_USER}" \
  --dbname "${DB_NAME}" \
  --clean --if-exists \
  --no-owner \
  "${BACKUP_FILE}"

echo "Restore complete. Next: run migrations (if the backup predates them) and"
echo "verify spot-checks: seller count, campaign budgets, recent audit rows."