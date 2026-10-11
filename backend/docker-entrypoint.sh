#!/usr/bin/env bash
# Entrypoint for every backend container (web, worker, beat).
set -euo pipefail

# Migrations and static collection belong to the web role alone. The worker and
# beat containers share this image, and three containers racing the same
# migration is how a schema ends up half-applied. Compose starts this one only
# once the database reports healthy.
if [ "${1:-}" = "gunicorn" ]; then
  echo "==> applying migrations"
  python manage.py migrate --noinput
  echo "==> collecting static files"
  python manage.py collectstatic --noinput
fi

exec "$@"
