#!/usr/bin/env bash
# Obtain the first Let's Encrypt certificate for $DOMAIN.
#
#   CERTBOT_EMAIL=you@example.com bash deploy/init-letsencrypt.sh
#
# Why this is not one command: nginx will not start without its certificate
# files, and the certificate cannot be issued until nginx is answering the ACME
# challenge. So this installs a throwaway self-signed certificate first, starts
# nginx, has Let's Encrypt replace it, and reloads. Run it once per hostname —
# renewal afterwards is a cron entry (see deploy/README.md §7).
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo ".env not found — copy .env.example to .env and fill it in first." >&2
  exit 1
fi

DOMAIN="$(grep -E '^DOMAIN=' .env | cut -d= -f2- | tr -d '\r')"
if [ -z "$DOMAIN" ]; then
  echo "DOMAIN is empty in .env" >&2
  exit 1
fi

# STAGING=1 exercises the flow against Let's Encrypt's staging CA, which has
# generous rate limits. Use it while getting DNS and ports right; the
# certificates it issues are not trusted by browsers.
STAGING="${STAGING:-0}"
STAGING_ARG=""
[ "$STAGING" != "0" ] && STAGING_ARG="--staging"

COMPOSE="docker compose --env-file .env"

echo "==> domain: $DOMAIN (staging=$STAGING)"

echo "==> placeholder certificate, so nginx has something to start with"
$COMPOSE run --rm --no-deps --entrypoint sh nginx -c "\
  apk add --no-cache openssl >/dev/null && \
  mkdir -p /etc/letsencrypt/live/$DOMAIN && \
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout /etc/letsencrypt/live/$DOMAIN/privkey.pem \
    -out /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
    -subj /CN=$DOMAIN"

echo "==> building and starting the stack"
# The whole stack, not just nginx. nginx resolves its upstream hostnames ("web",
# "frontend") from Docker's DNS as it loads its configuration, so it will refuse
# to start while those containers do not exist yet — and without nginx there is
# nothing to answer the ACME challenge. It starts here on the placeholder
# certificate and is reloaded with the real one below.
$COMPOSE up -d --build
sleep 5

echo "==> discarding the placeholder"
$COMPOSE run --rm --no-deps --entrypoint sh nginx -c "\
  rm -rf /etc/letsencrypt/live/$DOMAIN /etc/letsencrypt/archive/$DOMAIN && \
  rm -f /etc/letsencrypt/renewal/$DOMAIN.conf"

echo "==> requesting the real certificate (webroot, no downtime)"
$COMPOSE --profile tools run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  $STAGING_ARG \
  --email "${CERTBOT_EMAIL:?set CERTBOT_EMAIL=you@example.com}" \
  --agree-tos --no-eff-email \
  -d "$DOMAIN"

echo "==> reloading nginx"
$COMPOSE exec nginx nginx -s reload

echo
echo "TLS should be live at https://$DOMAIN"
echo "Verify with:  curl -I https://$DOMAIN/api/health/"
if [ "$STAGING" != "0" ]; then
  echo
  echo "You used STAGING=1, so the certificate is untrusted. Delete it and re-run"
  echo "without STAGING once DNS and ports are confirmed."
fi
