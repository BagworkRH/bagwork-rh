# 06 — Operations Runbook (Production Hardening)

Companion to `05_Deployment.md` Phase 8. This runbook covers the operational
procedures implemented in Phase 8: rate limiting, monitoring, backups,
restores, load testing, and recovery. All values are overridable through
environment variables (see `backend/.env.example`).

## 1. Rate limiting

DRF throttles are configured in `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`
(`backend/config/settings/base.py`) and applied globally via path-selective
classes in `backend/config/throttling.py`:

| Scope  | Path                                | Default rate |
| ------ | ----------------------------------- | ------------ |
| `auth`   | `/api/v1/auth/*` (register, login) | 10/hour per IP |
| `admin`  | `/api/v1/admin/*` (staff API)      | 120/hour per IP |
| `wallet` | `/api/v1/claims/*` mutations + the EIP-712 authorization GET | 30/hour per IP |
| `anon`   | every anonymous request            | 100/hour per IP |
| `user`   | every authenticated request        | 1000/hour per user |
| `submit` | `POST /api/v1/social/submissions/` (post intake that leads to a payout) | 20/hour per user |
| `health` | `/api/health/` (container probe + uptime monitors) | 1200/hour per IP |

`/api/health/` is deliberately *not* on the `anon` budget. The compose
healthcheck polls it every 30 seconds (120 requests/hour from one address) and an
uptime monitor adds more, so sharing the 100/hour anonymous bucket meant the
probe started receiving 429s an hour into every deploy — the `web` container went
unhealthy and nginx, which waits for it, never started. It keeps a ceiling of its
own so it is still not free to hammer.

Tune with `THROTTLE_AUTH`, `THROTTLE_ADMIN`, `THROTTLE_WALLET`,
`THROTTLE_ANON`, `THROTTLE_USER`, `THROTTLE_SUBMIT`, `THROTTLE_HEALTH`. Throttled
clients receive HTTP 429.

Each scoped throttle resolves its rate from settings on every request, so a
`THROTTLE_*` change applies without a restart of the web/worker processes. A
scope with no configured rate raises `ImproperlyConfigured` — a typo fails
loudly instead of silently disabling a limit.

> Development settings relax these to 100000/hour so local work and the test
> suite never trip them; production uses the env-driven values above.

## 2. Monitoring

- **Heartbeat** — Celery beat runs `apps.monitoring.tasks.heartbeat` every
  minute, refreshing the single-row `Heartbeat` table. `/api/health/` reports
  its freshness as `checks.heartbeat` (`ok` / `stale` / `unset`).
  `HEARTBEAT_STALE_SECONDS` (default 300) controls the staleness threshold.
- **Health endpoint** — `GET /api/health/` returns `status`, `database`,
  `redis`, `heartbeat`, and a `checks` block. Load balancers should poll it
  and alert on `status != ok` or `checks.heartbeat == stale`.
- **System checks** — `manage.py check --deploy` (gate your deploy pipeline on
  it) enforces production safety with `hardening.*` diagnostics:
  - `hardening.E001` SECRET_KEY is the insecure default (production only)
  - `hardening.E002` ALLOWED_HOSTS contains `*` (production only)
  - `hardening.W001` SENTRY_DSN not configured (warning)

  These are registered as *deployment* checks, so a plain `manage.py check`
  and `manage.py test` stay green on a development configuration (Django
  forces `DEBUG=False` for the whole test run). They are covered by
  `tests/test_monitoring.py`, and CI asserts that `check --deploy` really
  fails on an unsafe production config.
- **Error tracking** — when `SENTRY_DSN` is set, `config/sentry.py` boots the
  SDK in the web (WSGI/ASGI) and Celery processes. `SENTRY_TRACES_SAMPLE_RATE`
  controls tracing (default 0). PII is never attached (`send_default_pii=False`).
- **Structured logging & request ids** — every request is assigned an id
  (reused from an inbound `X-Request-ID`, else generated), echoed in the
  `X-Request-ID` response header and stamped on every log line, so a client
  error, its server logs, and its upstream trace share one id
  (`config/observability.py`). Set `LOG_FORMAT=json` to emit one JSON object per
  line for a log pipeline; the default is readable text. Celery tasks bind the
  same context with `bind_request_id(...)`, and extra fields go on a record with
  `logger.info("...", extra={"structured": {...}})` — the shape a
  provider-failure dashboard reads.
- **Provider metrics** — every provider API call is timed and logged with a
  structured outcome (`provider`, `operation`, `outcome`, `latency_ms`) by
  `apps/social/providers/metrics.py`, applied in `get_provider`. Chart failure
  rate and p95 latency per platform from those lines, and alert when a platform
  stops returning `outcome=ok` — the Phase 8 provider-outage signal.

### Alerting

Wire these to the on-call channel (pager/Slack). They are what turns a provider
outage — or a dead worker — into a page:

| Signal | Condition | Severity |
| --- | --- | --- |
| Health probe | `GET /api/health/` non-200, or `checks.heartbeat == "stale"` | page |
| Worker / beat dead | `checks.heartbeat == "unset"` for longer than one interval | page |
| Provider outage | `structured.outcome == "error"` rate for a platform above a small floor over ~5 min | page |
| Provider latency | p95 `structured.latency_ms` for a platform above its budget | ticket |
| Error spikes | Sentry: new / unhandled exception rate above a small floor | page |

Sentry covers the last row; the rest read the health endpoint and the structured
provider-metric lines. Keep thresholds beside the alert configuration, not in
code.

## 3. Backups (PostgreSQL)

```bash
cd backend
./scripts/backup_db.sh --check                # dump + verify the archive is readable
./scripts/restore_db.sh backups/bagwork_rh_20260701_120000.dump     # restore in place
./scripts/verify_restore.sh backups/bagwork_rh_20260701_120000.dump # the drill
```

- Custom-format dumps (`pg_dump --format=custom`) support selective restore.
- Managed Postgres (e.g. RDS/Supabase) usually snapshots automatically; the
  scripts are for self-hosted installs and for producing portable archives.
- **Tested restores are the definition of done.** `verify_restore.sh` is the
  one-command drill: it proves the archive is readable, restores it into a
  throwaway database (never the live one), compares row counts for the tables
  that matter, reports, and drops the throwaway. It exits non-zero on any
  mismatch, so a release pipeline can gate on it. Run it after every schema
  release.
- The drill's spot-check tables and the scripts' shell syntax are checked by
  `tests/test_backup_scripts.py`, so a renamed table fails the suite rather than
  turning the drill into a false PASS.

## 4. Load testing

```bash
cd backend
.venv/Scripts/activate          # or: source .venv/bin/activate
python scripts/load_test.py --url http://localhost:8001 --workers 20 --requests 400
```

The script reports request count, error rate, throughput, and p50/p95 latency
against `/api/health/` and `/api/v1/campaigns/`. For capacity planning use a
dedicated tool (k6 / Locust) hitting the full authenticated workflows
(register → link → join → verify → reward → claim).

## 5. Recovery procedures

1. **Incident** — pause claiming via `POST /api/v1/blockchain/control/`
   (`pause_claiming`) as a staff user, then triage.
2. **Data loss / corruption** — restore the latest verified backup into a
   fresh DB, run `python manage.py migrate --check` (or full migrate), point
   the app at it, then run the reconciliation task
   `apps.blockchain.tasks.reconcile_blockchain_ledger` and compare the
   internal ledger against the chain.
3. **Dead worker / lost beat** — check Redis (`INFO`), the heartbeat
   freshness in `/api/health/`, and the worker logs; restarting Celery beat
   restores the heartbeat within a minute.
4. **Secret rotation** — rotate `SECRET_KEY`, DB password, X OAuth
   credentials, and the testnet `CLAIM_SIGNER` in the secret manager, update
   `.env`/environment, restart all processes, and confirm
   `manage.py check --deploy` is green.

   Stored OAuth tokens are encrypted with a key derived from
   `SOCIAL_ENCRYPTION_KEY` (falling back to `SECRET_KEY`). Rotate it by setting
   the new `SOCIAL_ENCRYPTION_KEY` and re-encrypting existing rows from the old
   material — otherwise changing `SECRET_KEY` alone silently renders every
   stored token undecryptable:

   ```bash
   SOCIAL_ENCRYPTION_KEY=<new> SOCIAL_ENCRYPTION_KEY_OLD=<old> \
     python manage.py rotate_social_credentials      # add --dry-run to rehearse
   ```
5. **Post-incident** — write an audit-log entry (see `apps.audit`) noting what
   happened, who acted, and the resolution.

## 6. Staff console (`/ops`)

The back-office lives inside the product at **`https://<domain>/ops`**, not at
`/admin` — nginx routes `/admin/` to Django, so a page there would never be
reached. Both surfaces exist and they do different jobs:

| Surface | Use it for |
| --- | --- |
| `/ops` (Next.js) | Day-to-day review work: sellers, campaigns, posts, rewards, claims, risk |
| `/admin/` (Django) | Model-level edits with no purpose-built screen: token allowlist, `PlatformControl` pause switch, raw rows |

### Access

Sign in with a normal email/password as a user whose `is_staff` is true; an
**Ops** link then appears in the header. The route guard in
`frontend/app/ops/layout.tsx` is cosmetic only — every endpoint it calls is
`IsAdminUser` on the server, so hiding the UI is not what protects the data.

Grant access with:

```bash
python manage.py shell -c "from apps.accounts.models import User; u=User.objects.get(email='you@example.com'); u.is_staff=True; u.save()"
```

### Tabs

| Tab | Endpoint | Actions available |
| --- | --- | --- |
| Overview | `GET /api/v1/admin/overview/` | none (read-only dashboard) |
| Sellers | `GET /api/v1/admin/sellers/` | suspend / activate (`POST …/<id>/status/`) |
| Campaigns | `GET /api/v1/admin/campaigns/` | set status ACTIVE/PAUSED/ENDED/CANCELLED |
| Posts | `GET /api/v1/admin/posts/` | approve, or reject with a Spec 03 failure state |
| Rewards | `GET /api/v1/admin/rewards/` | approve → release (makes it claimable) → reverse |
| Claims | `GET /api/v1/admin/claims/` | mark failed with a reason |
| Risk | `GET /api/v1/admin/risk/` | dismiss / confirm / take into review, re-run the scan |
| Audit | `GET /api/v1/admin/audit-logs/` | none (append-only, read-only) |
| Settings | `GET /api/v1/admin/settings/` | none (reports *configured*, never secret values) |

Every action opens a confirmation dialog and records a reason in the audit
trail. Four distinctions are deliberate and worth knowing before you press a
button:

- **Suspend** stops a creator joining campaigns and claiming. It never deletes
  or rewrites rewards, claims or ledger entries.
- **Approve a post** marks it VERIFIED. It pays nothing — the reward engine
  calculates separately.
- **Release a reward** (APPROVED → AVAILABLE) is the step that makes money
  claimable, so it is a separate action from approving.
- **Mark a claim failed** does not burn the reward; the creator can claim again.

### Pausing the platform

`claiming_paused` has no button here on purpose. Set it in Django admin
(`PlatformControl`), which is also where the token allowlist is edited. The
Settings tab reports the current state so you can confirm it from `/ops`.
