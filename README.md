# Crypto Social Rewards Platform

A crypto-native platform inspired by the UsePaid workflow (original branding,
UI, and implementation) that connects **sellers/creators — X accounts,
wallets, campaigns, tracked posts, and crypto rewards**.

Built from the five master specifications in [`/docs`](docs):

| Doc | Topic |
| --- | --- |
| 01 | Product & UI |
| 02 | Backend, Database & API |
| 03 | X Tracking & Reward Engine |
| 04 | Blockchain & Wallet |
| 05 | Deployment, Security & Agent Instructions |

## Repository layout

```
backend/     Django + DRF API (apps: accounts, sellers, campaigns, social,
             rewards, wallets, blockchain, audit; Celery tasks; tests)
frontend/    Next.js 14 + TypeScript (dark crypto-native UI)
contracts/   Hardhat project (RewardToken, RewardDistributor + tests)
docs/        Specs 01–05 as markdown
.github/     CI workflow (backend lint+tests, frontend build)
```

## Quick start

### Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate           # (Linux: source .venv/bin/activate)
pip install -r requirements/dev.txt
copy .env.example .env           # fill in values (SQLite fallback works out of the box)
python manage.py migrate
python manage.py test tests      # 45 tests
python manage.py runserver       # http://localhost:8000/api/health/
```

### Frontend
```bash
cd frontend
npm install
npm run dev                      # http://localhost:3000
```

### Contracts
```bash
cd contracts/src/reward_token
npm install
npx hardhat test                 # unit tests for RewardDistributor
npx hardhat run scripts/deploy.ts --network sepolia
```

## Phase status

- **Phase 1 — Foundation:** ✅ repo, Django+DRF settings, CORS, Celery, ruff,
  CI, `/api/health/`, migrations.
- **Phase 2 — Auth & Seller:** ✅ custom User, register/login/logout/me,
  SellerProfile + secure unique seller codes (`SELLER-XXXXXX`), Wallet model,
  dashboard endpoint.
- **Phase 3 — Campaigns:** ✅ Campaign/Participation models, list/detail/join
  with eligibility checks (clear rejection reasons).
- **Phase 4 — X integration:** ✅ OAuth2+PKCE official adapter + clearly-marked
  mock, provider abstraction, link/disconnect, post submit/verify pipeline with
  failure states, metric snapshots, Celery tasks.
- **Phase 5 — Reward engine:** ✅ deterministic calculation service (fixed /
  impression / engagement / hybrid), caps, budget locking, approval flow,
  audit logging, reversal.
- **Phase 6 — Wallet & blockchain:** 🔶 claim model + idempotency + testnet
  contract scaffolding; on-chain listener/reconciliation in progress.
- **Phase 7 — Admin:** 🔶 Django admin configured; admin API/UI tightening.
- **Phase 8 — Hardening:** pending (rate limiting, monitoring, backups,
  load testing, recovery procedures).

## Security notes
- OAuth credentials encrypted at rest (AES-256-GCM, key derived from
  `SECRET_KEY`).
- Financial math uses `Decimal`; on-chain amounts use integer smallest units.
- Claims are idempotent; reward budget rows are locked under transaction.
- Never commit secrets; `.env` is git-ignored.

> Development-only mocks are clearly marked (`apps/social/providers/mock.py`,
> `RewardToken` contract) and are not wired into production paths.