#!/usr/bin/env bash
# One-command backup drill for bagworkRH — Spec 05 Phase 8 (tested restores).
#
# Proves a backup is *restorable* without touching the live database: it
# restores the archive into a throwaway database, compares row counts against
# the source for the tables that matter, reports, and drops the throwaway.
# "We have backups" becomes "we have restored backups".
#
# Usage:
#   ./scripts/verify_restore.sh <backup.dump> [--keep] [--scratch NAME]
#
# Exit code is non-zero if the archive is unreadable, the restore fails, or any
# spot-check count differs — so a release pipeline can gate on it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "${SCRIPT_DIR}")"

# table:label pairs compared between the source and the restored database.
# Keep in sync with the schema: tests/test_backup_scripts.py fails if a table
# listed here no longer exists.
SPOT_CHECKS=(
  "sellers_sellerprofile:sellers"
  "campaigns_campaign:campaigns"
  "campaigns_brandfunding:brand fundings"
  "rewards_reward:rewards"
  "wallets_claim:claims"
  "wallets_wallet:wallets"
  "social_socialaccount:social accounts"
  "blockchain_ledgerentry:ledger entries"
  "audit_auditlog:audit log"
)

KEEP=false
SCRATCH=""
BACKUP=""

while [ $# -gt 0 ]; do
  case "$1" in
    --keep) KEEP=true ;;
    --scratch) SCRATCH="${2:-}"; shift ;;
    -*) echo "error: unknown flag $1" >&2; exit 2 ;;
    *) BACKUP="$1" ;;
  esac
  shift
done

if [ -z "${BACKUP}" ]; then
  echo "usage: $0 <backup.dump> [--keep] [--scratch NAME]" >&2
  exit 2
fi
BACKUP="$(realpath "${BACKUP}")"
[ -f "${BACKUP}" ] || { echo "error: ${BACKUP} not found" >&2; exit 1; }

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
SCRATCH="${SCRATCH:-${DB_NAME}_verify_$(date +%Y%m%d_%H%M%S)}"

export PGPASSWORD="${DB_PASSWORD}"

cleanup() {
  if [ "${KEEP}" != true ]; then
    dropdb --host "${DB_HOST}" --port "${DB_PORT}" --username "${DB_USER}" \
      --if-exists "${SCRATCH}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

count() {  # count <dbname> <table>
  psql --host "${DB_HOST}" --port "${DB_PORT}" --username "${DB_USER}" \
    --dbname "$1" -tAc "SELECT count(*) FROM \"$2\"" | tr -d '[:space:]'
}

echo "1/4  integrity: reading archive table-of-contents"
pg_restore --list "${BACKUP}" >/dev/null

echo "2/4  scratch:   creating '${SCRATCH}'"
dropdb --host "${DB_HOST}" --port "${DB_PORT}" --username "${DB_USER}" \
  --if-exists "${SCRATCH}" >/dev/null 2>&1 || true
createdb --host "${DB_HOST}" --port "${DB_PORT}" --username "${DB_USER}" "${SCRATCH}"

echo "3/4  restore:   '${BACKUP}' -> '${SCRATCH}'"
pg_restore --host "${DB_HOST}" --port "${DB_PORT}" --username "${DB_USER}" \
  --dbname "${SCRATCH}" --no-owner "${BACKUP}"

echo "4/4  spot-check: source vs restored row counts"
FAILED=0
for entry in "${SPOT_CHECKS[@]}"; do
  table="${entry%%:*}"
  label="${entry#*:}"
  src="$(count "${DB_NAME}" "${table}")"
  dst="$(count "${SCRATCH}" "${table}")"
  if [ "${src}" = "${dst}" ]; then
    printf '  [OK]   %-16s %s\n' "${label}" "${src}"
  else
    printf '  [FAIL] %-16s source=%s restored=%s\n' "${label}" "${src}" "${dst}"
    FAILED=1
  fi
done

if [ "${FAILED}" -ne 0 ]; then
  echo "Drill FAILED: restored database does not match the source." >&2
  exit 1
fi
echo "Drill PASSED: '${BACKUP}' restores cleanly and matches the source."
if [ "${KEEP}" = true ]; then
  echo "Scratch database kept: ${SCRATCH}"
fi
