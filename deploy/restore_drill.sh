#!/usr/bin/env bash
# Restore drill for the compose deployment.
#
#   bash deploy/restore_drill.sh
#
# Takes the newest dump in deploy/backups, restores it into a throwaway database
# inside the `db` container, compares row counts table by table against the live
# database, then drops the throwaway. Exits non-zero on any drift, so it can be
# scheduled.
#
# Why this exists: `backup.sh` proves an archive is *readable*; only a restore
# proves it is *correct*. An untested backup is a hope, and the failure you care
# about is the one that appears the first time you actually need it.
set -euo pipefail

cd "$(dirname "$0")"

[ -f .env ] || { echo ".env not found" >&2; exit 1; }

DB_NAME="$(grep -E '^DB_NAME=' .env | cut -d= -f2- | tr -d '\r')"
DB_USER="$(grep -E '^DB_USER=' .env | cut -d= -f2- | tr -d '\r')"
COMPOSE="docker compose --env-file .env"
DRILL_DB="drill"

DUMP="$(ls -t backups/*.dump 2>/dev/null | head -1)"
if [ -z "$DUMP" ]; then
  echo "no dump in backups/ — run deploy/backup.sh first" >&2
  exit 1
fi
echo "==> drill source: $DUMP ($(du -h "$DUMP" | cut -f1))"

$COMPOSE exec -T db psql -U "$DB_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS ${DRILL_DB}" >/dev/null
$COMPOSE exec -T db psql -U "$DB_USER" -d postgres \
  -c "CREATE DATABASE ${DRILL_DB}" >/dev/null

echo "==> restoring into ${DRILL_DB}"
$COMPOSE exec -T db pg_restore -U "$DB_USER" -d "$DRILL_DB" --no-owner < "$DUMP"

$COMPOSE exec -T db psql -U "$DB_USER" -d "$DB_NAME" -At \
  -c "select relname from pg_stat_user_tables order by relname" > /tmp/drill_tables.txt

drift=0
while read -r table; do
  live="$($COMPOSE exec -T db psql -U "$DB_USER" -d "$DB_NAME" -At -c "select count(*) from ${table}")"
  restored="$($COMPOSE exec -T db psql -U "$DB_USER" -d "$DRILL_DB" -At -c "select count(*) from ${table}")"
  if [ "$live" != "$restored" ]; then
    echo "DRIFT ${table}: live=${live} restored=${restored}"
    drift=$((drift + 1))
  fi
done < /tmp/drill_tables.txt

echo "==> compared $(wc -l < /tmp/drill_tables.txt) tables, drift=${drift}"

$COMPOSE exec -T db psql -U "$DB_USER" -d postgres \
  -c "DROP DATABASE ${DRILL_DB}" >/dev/null

if [ "$drift" -eq 0 ]; then
  echo "DRILL_OK"
else
  echo "DRILL_FAILED: ${drift} table(s) differ" >&2
  exit 1
fi
