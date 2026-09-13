# 05 — Deployment, Security & AI Coding Agent Instructions

Execution document for an AI coding agent. The agent implements the platform
from the previous four specifications **without inventing conflicting
requirements**.

## Source of truth (priority order)
1. Explicit user instruction in the current task
2. This document
3. Documents 01–04
4. Existing project conventions

If requirements conflict: stop and identify the conflict.

## Repository structure
```
/backend     manage.py · config/ · apps/{accounts,sellers,campaigns,social,
             rewards,wallets,blockchain,audit}/ · requirements/ · tests/
/frontend    app/ · components/ · lib/ · hooks/ · services/ · types/
/contracts   src/ · test/ · scripts/
/docs        01_Product_UI.md 02_Backend_API.md 03_X_Tracking.md
             04_Blockchain.md 05_Deployment.md
```

## Implementation phases
1. **Foundation** — repo structure, Django, PostgreSQL, DRF, frontend, env,
   linting, CI, health endpoint. Acceptance: backend starts, frontend starts,
   migrations work, tests run.
2. **Auth & Seller** — auth, seller profile, seller code generation, wallet
   model, dashboard skeleton. Acceptance: account creation, unique seller code,
   profile view.
3. **Campaigns** — CRUD, listing, detail, participation, eligibility rules.
4. **X integration** — OAuth, account linking, provider abstraction, post
   discovery, verification pipeline, metrics snapshots.
5. **Reward engine** — calculation service, reward records, budget accounting,
   caps, approval flow, audit logging.
6. **Wallet & blockchain** — wallet connection, ownership signatures, testnet
   contract, claim auth, claim tx, event listener, reconciliation.
7. **Admin** — sellers, campaigns, post review, reward review, claims,
   fraud/risk queue, audit logs.
8. **Production hardening** — rate limiting, monitoring, backups, error
   tracking, secret management, security review, load testing, recovery.

## Environment variables
`DATABASE_URL · REDIS_URL · DJANGO_SECRET_KEY · X_CLIENT_ID ·
X_CLIENT_SECRET · X_REDIRECT_URI · FRONTEND_URL · RPC_URL · CHAIN_ID ·
REWARD_TOKEN_ADDRESS · CONTRACT_ADDRESS · CLAIM_SIGNER` + monitoring creds.
Never commit secrets.

## Deployment
Frontend: managed platform (e.g. Vercel). Backend: Gunicorn on Linux/container,
Nginx reverse proxy, HTTPS. Workers: Celery worker + beat, Redis broker.
Database: managed PostgreSQL, automated backups, tested restores.

## Production checklist
DEBUG=False · HTTPS · secure cookies · allowed hosts · restricted CORS · CSRF
· secured DB creds · rotated secrets · error monitoring · rate limits · admin
MFA · secured wallet signing · reviewed smart contracts · testnet done ·
verified backups.

## AI coding-agent behavior
1. Read all five documents before coding.
2. Inspect existing code before changing it.
3. Preserve working functionality.
4. Small, logically grouped changes.
5. Run tests after each major phase.
6. Report changed files.
7. Report tests run and results.
8. Never fabricate successful API calls.
9. Never hard-code credentials.
10. No mock blockchain success in production code.
11. Clearly mark development mocks.
12. Ask for credentials only when needed.
13. Use migrations for schema changes.
14. Keep business logic out of React components.
15. Blockchain logic isolated behind services.
16. X API logic behind a provider adapter.
17. Financial operations idempotent.
18. Audit logs for sensitive actions.

## Definition of done (MVP)
Seller onboard · X linked · wallet linked & verified · seller code · campaign
created · seller joins · qualifying post discovered · post verified · metrics
refreshed · reward calculated · reward approved · seller claims testnet token ·
claim recorded on-chain and in DB · admin sees full audit trail · automated
tests cover critical financial/permission logic.

## MVP exclusions
Multiple blockchains (unless required) · DAO governance · NFT marketplace ·
referral tree · anonymous cash-out · AMM · unverified engagement scraping ·
anything bypassing X restrictions.

V2 candidates: multiple chains, more reward models, self-service campaigns,
referrals, advanced fraud scoring, analytics, third-party API, mobile app.