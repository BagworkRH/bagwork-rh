# Deploying bagworkRH on one always-free VM

Everything in this directory exists so that a single Oracle Cloud Always Free
instance runs the whole platform for £0/month, indefinitely.

## What gets deployed

```
                    ┌──────────────────────────────┐
   internet ──443──▶│ nginx  (TLS, the only public │
                    │        process)              │
                    └───────┬──────────────┬───────┘
                     /api/  │              │  everything else
                            ▼              ▼
                   ┌──────────────┐  ┌──────────────┐
                   │ web          │  │ frontend     │
                   │ gunicorn +   │  │ Next.js      │
                   │ Django       │  │ (next start) │
                   └──┬────────┬──┘  └──────────────┘
                      │        │
              ┌───────▼──┐  ┌──▼──────────┐
              │ postgres │  │ redis       │
              └──────────┘  └──┬──────────┘
                               │
                     ┌─────────┴──────────┐
                     │ worker      beat   │
                     │ (Celery, same image)│
                     └────────────────────┘
```

**One domain serves both halves.** The site and the API share
`https://<DOMAIN>`, with nginx routing `/api/` and `/admin/` to Django and
everything else to Next.js. That is a deliberate simplification over the
`api.`-subdomain split mentioned in `docs/07`: same-origin means nothing is
cross-origin, so there is no CORS policy to get wrong, no cross-site cookie
problems, and exactly one hostname for X to have registered as an OAuth
callback. If you later want the split, add a second `server` block — but you
must then set `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` for both hosts.

**One copy of each service.** `beat` in particular must never be scaled: two
schedulers double-fire every periodic task, which here means duplicate
discovery polls and duplicate reconciliation.

## Why this shape

The app runs **Celery worker and beat continuously** — discovery polls every 5
minutes, claim events every 2, reconciliation every 6 hours. Free PaaS tiers
either sleep an idle web service or charge for background workers, and Render's
free Postgres is deleted after 30 days. A free-forever VM is the only option
that actually runs this workload without rewriting the task layer.

## 1. The VM

Oracle Cloud → Create Instance:

| Setting | Value |
|---|---|
| Image | Ubuntu 24.04 (aarch64) |
| Shape | **VM.Standard.A1.Flex**, 2 OCPU / 12 GB (inside the Always Free allowance) |
| Boot volume | 50 GB is plenty |
| SSH key | upload yours |

If creation fails with *"out of host capacity"*, try another availability
domain or wait — Always Free capacity in popular regions is genuinely scarce.

**Open the ports.** Both of these, or nginx stays unreachable from the internet:

1. OCI console → VCN → Security List → add ingress rules for TCP **80** and **443** from `0.0.0.0/0`.
2. `bootstrap.sh` handles the instance's own firewall (including Oracle's
   iptables rules, which reject non-SSH traffic independently of any console
   rule — the single most common cause of "it works locally but not from the
   internet").

```bash
sudo apt-get update && sudo apt-get install -y git
git clone git@github.com:BagworkRH/bagwork-rh.git
cd bagwork-rh
bash deploy/bootstrap.sh        # Docker, compose plugin, ufw, OCI iptables
newgrp docker                   # or log out and back in
```

## 2. DNS

Point an `A` record at the instance's public IP:

| Name | Type | Value |
|---|---|---|
| `@` (or `www`) | A | your instance's public IPv4 |

If you use Cloudflare, set the record to **DNS only** (grey cloud) for this
first setup — the orange cloud proxies traffic and can interfere with the ACME
challenge. Turn it back on afterwards if you want their CDN.

Confirm it has propagated before requesting a certificate; Let's Encrypt
validates over HTTP against this name and will fail while it still resolves
elsewhere:

```bash
dig +short bagworkrh.com
```

## 3. Configuration

```bash
cp deploy/.env.example deploy/.env
python3 -c "import secrets; print(secrets.token_urlsafe(64))"   # run 3x
```

Fill in `deploy/.env`:

- `DOMAIN` / `PUBLIC_URL` — must match the DNS record exactly.
- `SECRET_KEY`, `DB_PASSWORD`, `SOCIAL_ENCRYPTION_KEY` — the three generated values.
- `X_CLIENT_ID` / `X_CLIENT_SECRET` — from the X developer portal.
- `X_REDIRECT_URI` — `https://<DOMAIN>/api/v1/x/x/callback/` (note the doubled
  `x`; see `docs/09`).
- `FRONTEND_URL` — `https://<DOMAIN>`.
- `RPC_URL` and the chain values — use a paid RPC provider in production, since
  the public endpoints are rate-limited and this process polls continuously.

`deploy/.env` is gitignored via the root `.env` rule. It is the single source of
production configuration: compose reads it for interpolation **and** mounts it
into the app containers.

> **The one that bites people:** `NEXT_PUBLIC_API_URL` is baked into the browser
> bundle at **build** time, not read at runtime. `docker-compose.yml` passes it
> as a build arg from `PUBLIC_URL`, so changing the public URL means rebuilding
> the frontend image (`--build`), not just restarting the container.

## 4. First launch (build, then TLS)

```bash
CERTBOT_EMAIL=you@example.com bash deploy/init-letsencrypt.sh
```

This both builds the stack and gets its certificate, because the two
requirements are circular: nginx will not start without certificate files, and
the certificate cannot be issued before nginx is serving the ACME challenge. The
script:

1. installs a throwaway self-signed certificate, so nginx has something to load;
2. builds and starts the whole stack — everything, not just nginx, because nginx
   resolves its upstream hostnames at startup and refuses to boot while the
   `web` and `frontend` containers do not exist;
3. deletes the placeholder and has Let's Encrypt replace it over the webroot;
4. reloads nginx.

Use `STAGING=1` in front of it while DNS is still settling — staging has
generous rate limits, production allows five failures an hour.

## 5. Create the admin and verify

```bash
cd deploy
docker compose exec web python manage.py createsuperuser
docker compose ps                       # everything should read "healthy"
curl -s https://bagworkrh.com/api/health/ | python3 -m json.tool
```

`status` should be `ok`. `redis` should be `ok` too — if it is `error`, the
worker cannot consume anything. `heartbeat` is written by the beat container
every minute, so give it a minute after the first start before believing it.

Then walk the app: sign up, connect X, join a campaign, and watch
`docker compose logs -f web worker beat` for the discovery poll landing.

Subsequent deploys do not need the TLS script — just §8.

## 6. Point X at the production callback

In the X developer portal, register the production callback **alongside** the
local one:

```
https://bagworkrh.com/api/v1/x/x/callback/
```

Keep `http://127.0.0.1:8001/api/v1/x/x/callback/` for local work. X matches the
string exactly, so the scheme and host both have to be right — the failure mode
when they are not is X's generic *"Something went wrong"* on the consent screen
and no callback ever arriving (`docs/09` covers this in full).

## 7. Backups

`backend/scripts/backup_db.sh` assumes a PostgreSQL server on the host; here the
server is in the `db` container, so `deploy/backup.sh` runs the dump and its
verification inside that container instead.

```bash
crontab -e
```

```cron
# 03:10 nightly — database dump, verify, prune to 14 days
10 3 * * * cd /home/ubuntu/bagwork-rh/deploy && bash backup.sh 14 >> /var/log/bagworkrh-backup.log 2>&1

# Monday 04:20 — renew certificates if <30 days remain, then reload nginx
20 4 * * 1 cd /home/ubuntu/bagwork-rh/deploy && docker compose --profile tools run --rm certbot renew --webroot -w /var/www/certbot >> /var/log/bagworkrh-cert.log 2>&1 && docker compose exec nginx nginx -s reload
```

Then get those dumps off the machine, and **run the restore drill** — an
untested backup is a hope, not a backup.

## 8. Deploying a change

```bash
git pull
cd deploy && docker compose --env-file .env up -d --build
```

Docker rebuilds only what changed, and migrations run on web startup. If you
changed `PUBLIC_URL`, the frontend rebuild is what makes it take effect.

## 9. Troubleshooting

| Symptom | Cause |
|---|---|
| **Infinite redirect** / `ERR_TOO_MANY_REDIRECTS` | nginx is not sending `X-Forwarded-Proto`, so Django's `SECURE_SSL_REDIRECT` bounces it back. Check the `proxy_set_header` lines in `deploy/nginx/app.conf.template`. |
| **502 Bad Gateway** | The upstream container is down or still starting. `docker compose ps` then `docker compose logs web`. |
| **Admin loads unstyled** | `collectstatic` has not populated the shared `static` volume, or nginx's `/static/` alias is wrong. `docker compose exec web python manage.py collectstatic --noinput`. |
| **Reachable locally, not from the internet** | Almost always the OCI security list or the instance's own iptables (see §1). Check both. |
| **Certificate request fails** | DNS has not propagated, port 80 is blocked, or you have hit Let's Encrypt's rate limit (5 failures/hour). Test with `STAGING=1`. |
| `redis: "error"` in health | The `redis` container is down or `REDIS_URL` is wrong — it must say `redis://redis:6379/0`, the compose service name, not `localhost`. |
| `heartbeat: "unset"` | The `beat` container is not running. Scheduled work is not happening. |

## 10. What this does and does not give you

**Free, indefinitely:** 2 OCPU / 12 GB ARM, 200 GB disk, 10 TB/month egress —
comfortably more than this stack needs.

**Not included, and yours to own:** OS updates, off-machine backups, the
restore drill, and responding to alerts. `docs/06_Operations.md` describes the
backup, rotation and alerting procedures; this document is only how to get the
boxes running.

