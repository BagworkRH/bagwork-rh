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

Tune with `THROTTLE_AUTH`, `THROTTLE_ADMIN`, `THROTTLE_WALLET`,
`THROTTLE_ANON`, `THROTTLE_USER`, `THROTTLE_SUBMIT`. Throttled clients receive HTTP 429.

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

## 3. Backups (PostgreSQL)

```bash
cd backend
./scripts/backup_db.sh                      # -> backups/bagwork_rh_*.dump
./scripts/restore_db.sh backups/bagwork_rh_20260701_120000.dump
```

- Custom-format dumps (`pg_dump --format=custom`) support selective restore.
- Managed Postgres (e.g. RDS/Supabase) usually snapshots automatically; the
  script is for self-hosted installs and for producing portable archives.
- **Tested restores** are part of the definition of done: restore into a
  staging DB after every schema release and spot-check seller/campaign/reward
  totals.

## 4. Load testing

```bash
cd backend
.venv/Scripts/activate          # or: source .venv/bin/activate
python scripts/load_test.py --url http://localhost:8000 --workers 20 --requests 400
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
5. **Post-incident** — write an audit-log entry (see `apps.audit`) noting what
   happened, who acted, and the resolution.