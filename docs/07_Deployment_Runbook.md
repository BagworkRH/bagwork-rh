# 07 — Deployment Runbook (Robinhood Chain)

Execution guide for taking bagworkRH from a clean checkout to a live
deployment on **Robinhood Chain**, an Arbitrum Layer-2 on Ethereum using ETH
for gas. Follows `05_Deployment.md` §Deployment and `06_Operations.md` §5.

## Chain reference

| | Testnet | Mainnet |
| --- | --- | --- |
| Chain ID | `46630` | `4663` |
| Public RPC | `https://rpc.testnet.chain.robinhood.com` | `https://rpc.mainnet.chain.robinhood.com` |
| Explorer | `https://explorer.testnet.chain.robinhood.com` | `https://robinhoodchain.blockscout.com` |
| Gas token | ETH | ETH |

> The public endpoints are **rate-limited and not intended for production**.
> Robinhood recommends a provider (Alchemy, QuickNode, Chainstack, dRPC,
> Blockdaemon, Validation Cloud) for anything beyond prototyping. Set
> `RH_RPC_URL_TESTNET` / `RH_RPC_URL` for Hardhat and `RPC_URL` for the
> backend. The event listener polls the chain continuously, so a rate limit
> here shows up as missed `RewardClaimed` events.

Both chains were verified live before this runbook was written:
`eth_chainId` returns `0xb626` (46630) at block 125,723,791 on testnet and
`0x1237` (4663) on mainnet.

## Order of operations

1. Pre-flight checks
2. Fund a deployer wallet
3. Deploy the contracts
4. Verify the on-chain domain separator
5. Configure the backend
6. Smoke-test the claim flow
7. Deploy the application
8. Mainnet repeat

## 1. Pre-flight

```bash
git clone https://github.com/BagworkRH/bagwork-rh.git
cd bagwork-rh

# Backend
cd backend
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements/prod.txt
cp .env.example .env

# Frontend
cd ../frontend && npm ci
```

Confirm the whole toolchain is green **before** touching a chain:

```bash
cd backend      && .venv/bin/python manage.py test tests   # 171 tests
cd ../contracts/src/reward_token && npm ci && npx hardhat test   # 4 tests
cd ../../frontend && npm run build
```

## 2. Fund a deployer wallet

> **Verified 2026-09-27.** Both RPCs respond with the expected chain ids:
> testnet `0xb626` (46630), mainnet `0x1237` (4663). The backend's `CHAIN_ID`
> must match whichever network you deploy to; it currently defaults to testnet.
>
> **Cost: $0.** Testnet ETH comes from the Robinhood Chain faucet, and a
> two-contract deploy on this Arbitrum L2 costs cents. **Do not fund mainnet
> yet.** `RewardToken.sol` is an owner-mintable development token with no supply
> cap, and `RewardDistributor.sol` carries an explicit "no production funds
> until security review" warning. Both warnings are correct.
>
> The mainnet launch carried a 90-day gas rebate that a secondary source reports
> ending 29 September 2026. Unverified against official docs -- check before
> budgeting, though it barely moves the number.

Generate a **fresh, dedicated** key. Never reuse a key that has touched
mainnet for anything else, and never commit it.

```bash
node -e "const {Wallet}=require('ethers');const w=Wallet.createRandom();\
console.log('address:', w.address); console.log('key:', w.privateKey)"
```

Fund it with testnet ETH from the Robinhood Chain faucet, then confirm:

- **Official faucet: <https://faucet.testnet.chain.robinhood.com>** — confirmed on
  Robinhood's own support page ("You can get testnet tokens at
  faucet.testnet.chain.robinhood.com"). Use this first.
- Fallback: <https://www.alchemy.com/faucets/robinhood-testnet> (0.1 ETH / 24h,
  no account) — but Alchemy's eligibility requires ~0.001 ETH **on Ethereum
  mainnet plus real mainnet activity**, which a freshly generated deployer key
  will not have. Do not expect this one to work for a new address.

A two-contract deploy on this L2 costs cents, so one drip is ample. Never send
mainnet ETH to this key.

```bash
node -e "const {JsonRpcProvider,formatEther}=require('ethers');\
new JsonRpcProvider('https://rpc.testnet.chain.robinhood.com')\
.getBalance(process.argv[1]).then(b=>console.log(formatEther(b),'ETH'))" 0xYOUR_ADDRESS
```

## 3. Deploy the contracts

```bash
cd contracts/src/reward_token
export DEPLOYER_PRIVATE_KEY=0xYOUR_TESTNET_KEY
npx hardhat run scripts/deploy.ts --network robinhoodTestnet
```

The script deploys `RewardToken` then
`RewardDistributor(token, signer, treasury)` and prints every address you need.
It **refuses to run** if the EIP-712 domain name in the contract does not match
`EIP712_DOMAIN_NAME` (default `bagworkRH`) — see §9.

Set `TREASURY_ADDRESS` to a **multisig** before mainnet. If it is unset the
script falls back to the deployer EOA and prints a warning, because a deployer
key that can also withdraw fees is a single point of failure for the treasury.

Record:

| Variable | Value |
| --- | --- |
| `CHAIN_ID` | `46630` |
| `REWARD_TOKEN_ADDRESS` | printed by the script |
| `CONTRACT_ADDRESS` | printed by the script |
| `TREASURY_ADDRESS` | printed by the script (multisig on mainnet) |
| `CLAIM_SIGNER_ADDRESS` | printed by the script |
| `CLAIM_SIGNER` | the deployer key (testnet only) |

> On mainnet, use a **separate** signing key from the deployer: the deployer
> only ever needs to deploy, whereas `CLAIM_SIGNER` signs every claim
> authorization and is therefore exposed for its whole lifetime. Deploy with
> key A, then set `CLAIM_SIGNER` to a key B that never leaves the secret store.

## 4. Verify the on-chain domain separator

The most important check in this runbook. `DOMAIN_SEPARATOR` is computed **in
the constructor** and can never change, so a wrong value means every
authorization the backend signs is rejected — for the life of the contract.

```bash
# On-chain value
node -e "const {JsonRpcProvider,Contract}=require('ethers');\
new Contract(process.argv[1],['function DOMAIN_SEPARATOR() view returns (bytes32)'],\
new JsonRpcProvider('https://rpc.testnet.chain.robinhood.com'))\
.DOMAIN_SEPARATOR().then(v=>console.log(v))" $CONTRACT_ADDRESS
```

```bash
# Backend value, for the same chain id + address
cd backend && .venv/bin/python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.dev')
django.setup()
from apps.blockchain import signing
print('0x' + signing.build_domain_separator(46630, '$CONTRACT_ADDRESS').hex())"
```

The two strings **must be identical**. If they differ, redeploy — it cannot be
patched.

## 5. Configure the backend

Fill in `backend/.env` (kept out of git by `.gitignore`):

```ini
DEBUG=0
SECRET_KEY=<64+ random chars, from a secret manager>
ALLOWED_HOSTS=api.bagworkrh.com
CSRF_TRUSTED_ORIGINS=https://bagworkrh.com
CORS_ALLOWED_ORIGINS=https://bagworkrh.com

DB_ENGINE=django.db.backends.postgresql
DB_NAME=bagwork_rh
DB_USER=...
DB_PASSWORD=...
DB_HOST=...
DB_PORT=5432
REDIS_URL=redis://...

X_CLIENT_ID=...
X_CLIENT_SECRET=...
X_REDIRECT_URI=https://api.bagworkrh.com/api/v1/x/callback/
X_PROVIDER=official

RPC_URL=https://robinhood-testnet.g.alchemy.com/v2/<KEY>   # provider, not public RPC
CHAIN_ID=46630
REWARD_TOKEN_ADDRESS=0x...
CONTRACT_ADDRESS=0x...
CLAIM_SIGNER=0x...            # secret manager only
CLAIM_SIGNER_ADDRESS=0x...
TOKEN_DECIMALS=18
EIP712_DOMAIN_NAME=bagworkRH  # must match RewardDistributor.sol

SENTRY_DSN=https://...@o0.ingest.sentry.io/1
ENVIRONMENT=production
```

Then gate on the deploy check, which fails fast on unsafe production config:

```bash
.venv/bin/python manage.py check --deploy
.venv/bin/python manage.py migrate
```

## 6. Smoke-test the claim flow

With the backend running, confirm the chain wiring before letting users in:

```bash
curl -s -H "Authorization: Token $STAFF_TOKEN" \
  https://api.bagworkrh.com/api/v1/blockchain/status/ | python -m json.tool
```

Expect `"chain_enabled": true`, `"signer_configured": true`, and
`"signer_address"` matching `CLAIM_SIGNER_ADDRESS`.

Then, end to end, as a seller:

1. Onboard, connect a wallet, verify ownership.
2. Join a funded testnet campaign and publish a qualifying post.
3. Let it be verified, then have an admin approve the reward.
4. `GET /api/v1/claims/<id>/authorization/` — returns the EIP-712 payload and
   calldata for the wallet to sign.
5. Submit it and confirm the receipt.
6. `POST /api/v1/blockchain/listen/` to reconcile immediately rather than
   waiting for the beat schedule.
7. `apps.blockchain.tasks.reconcile_blockchain_ledger` should report no drift.

## 7. Deploy the application

**Frontend** — Vercel or any Next.js host:

```bash
cd frontend
vercel --prod            # or connect the repo in the dashboard
```

Set `NEXT_PUBLIC_API_URL=https://api.bagworkrh.com` in the host's environment.

**Backend** — Gunicorn behind Nginx with TLS:

```bash
pip install gunicorn
gunicorn config.wsgi:application \
  --chdir backend --env-file backend/.env \
  --workers 4 --timeout 60 --bind 127.0.0.1:8000
```

**Workers** — both required, or claims never reconcile:

```bash
celery -A config worker -l info     # task execution
celery -A config beat  -l info      # schedules the listener + heartbeat
```

`beat` must run in exactly one place: a second beat double-fires every
scheduled task.

## 8. Mainnet repeat

Only after a full testnet cycle, including a restore drill.

1. Fund a fresh mainnet key. **Verify the chain ID is `4663` before sending.**
2. `npx hardhat run scripts/deploy.ts --network robinhood`
3. Repeat the §4 comparison with `CHAIN_ID=4663`. It **will differ** from the
   testnet value, and must match the backend for *that* chain id.
4. Point `RPC_URL`, `CHAIN_ID`, `CONTRACT_ADDRESS`, `REWARD_TOKEN_ADDRESS`,
   `CLAIM_SIGNER*` at mainnet.
5. Use a **different** `CLAIM_SIGNER` than testnet.
6. Re-run `manage.py check --deploy` and the §6 smoke test with a
   deliberately tiny reward.

## 9. Warning: the EIP-712 domain is permanent

`DOMAIN_SEPARATOR` is hashed in the constructor from the literal string in
`RewardDistributor.sol`. Renaming the product after deployment does **not**
update the contract, and the backend would then sign under a domain the
deployed contract rejects. The deploy script refuses to run on a mismatch, and
`EIP712_DOMAIN_NAME` lets the backend and contract be compared explicitly. If
they ever diverge, **redeploy the contract** — the existing one cannot be
repaired.

## Emergency controls

```bash
# Pause claiming (admin token required)
curl -X POST https://api.bagworkrh.com/api/v1/blockchain/control/ \
  -H "Authorization: Token $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"pause_claiming"}'
```

Use `resume_claiming` to reverse. Rotating a compromised claim signer is
`services.rotate_claim_signer(new_key, actor=...)`; note that authorizations
signed by the old key stay valid until their deadline, so pause first.

Wider incident, backup and recovery procedures live in
[`06_Operations.md`](06_Operations.md).



