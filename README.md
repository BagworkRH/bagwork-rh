# bagworkRH

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
python manage.py test tests      # 171 tests
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

## Blockchain configuration (Phase 6)

Set these in `backend/.env` (see `.env.example`):

| Variable | Purpose |
| -------- | ------- |
| `RPC_URL` | EVM JSON-RPC endpoint (e.g. Sepolia public RPC) |
| `CHAIN_ID` | Chain ID (defaults to 11155111 / Sepolia) |
| `CONTRACT_ADDRESS` | Deployed `RewardDistributor` address |
| `REWARD_TOKEN_ADDRESS` | Reward token contract address |
| `CLAIM_SIGNER` | **Testnet only** private key that signs claim authorizations |

Until `CONTRACT_ADDRESS`/`CLAIM_SIGNER` are configured, claims are created with
`authorization_ready: false` and the listener/reconciliation Celery tasks report
`status: "disabled"` instead of failing — the rest of the platform keeps working.

Tokens must be allowlisted in the `TokenConfig` table (Django admin) before their
claims can be authorized; token decimals are read from that row.

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
- **Phase 6 — Wallet & blockchain:** ✅ EVM wallet connect + nonce-signature
  ownership verification, token allowlist (`TokenConfig`) with per-token
  decimals, EIP-712 claim authorization signed server-side, ABI-encoded claim
  calldata (cross-validated against ethers), transaction submission tracking,
  `RewardClaimed` event listener + reconciliation, emergency controls
  (pause/disable/rotate), internal accounting ledger. Solidity
  `RewardDistributor` + `RewardToken` with Hardhat tests. Live testnet
  deployment (contract addresses/RPC) is the remaining integration step.
- **Phase 7 — Admin:** ✅ staff back-office API (sellers, campaigns, post
  review, reward review, claims, fraud/risk review queue), Django admin
  configured, audited admin actions.
- **Phase 8 — Hardening:** 🔶 rate limiting (path-scoped DRF throttles for
  auth/admin/wallet surfaces + anonymous/authenticated baselines), monitoring
  (Celery heartbeat, richer `/api/health/`, deployment system checks via
  `manage.py check --deploy`), error tracking (Sentry, opt-in via
  `SENTRY_DSN`), PostgreSQL backup/restore scripts, concurrency smoke-test
  script, and an operations runbook in
  [`docs/06_Operations.md`](docs/06_Operations.md).

## Security notes
- OAuth credentials encrypted at rest (AES-256-GCM, key derived from
  `SECRET_KEY`).
- Financial math uses `Decimal`; on-chain amounts use integer smallest units.
- Claims are idempotent; reward budget rows are locked under transaction.
- Claim authorizations are EIP-712 signed with a dedicated `CLAIM_SIGNER`
  (never the app secret), with expiry, nonce, chain-ID and contract-address
  replay protection.
- Never commit secrets; `.env` and `.env.local` are git-ignored.

> Development-only mocks are clearly marked (`apps/social/providers/mock.py`,
> `RewardToken` contract) and are not wired into production paths.