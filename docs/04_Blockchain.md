# 04 — Blockchain & Wallet Specification

Allow sellers to connect wallets, view crypto rewards, and claim eligible
rewards securely. Start with **one EVM-compatible chain**; modular config so
more chains can be added later.

## Wallet connection
Reputable wallet connection protocol/provider. Supported wallets depend on
provider availability. **Never request**: seed phrase, private key, wallet
password.

## Wallet verification
1. Read address and chain ID.
2. Ask user to sign a platform-specific nonce message.
3. Verify signature server-side.
4. Mark wallet verified.
5. Store address normalized for the chain.

**Never treat an address alone as proof of ownership.** If the wallet is on
the wrong network: explain the required network, request a switch through the
wallet provider, never silently assume the switch succeeded.

## Smart contract architecture
Audited, minimal contracts. Reward distributor responsibilities:
- authorized reward distributor
- token address
- claim allocation
- claimed status
- emergency pause
- ownership/admin role
- event emission

Claim model: off-chain system calculates approved reward → backend signs an
authorization/claim message → seller submits claim transaction → contract
verifies authorization and **prevents replay**.

## Replay protection
Each claim authorization includes: wallet, reward/campaign id, token, amount,
nonce, expiry/deadline, chain ID, contract address/domain separation.

## Claim flow
1. Seller opens Available Rewards.
2. Platform verifies wallet and eligibility.
3. Backend generates claim authorization.
4. Frontend asks wallet to submit the transaction.
5. Contract validates authorization.
6. Transaction mined.
7. Backend listener sees the event.
8. Claim marked `CLAIMED`.
9. Transaction hash shown to the seller.

Transaction states: CREATED · SIGNING · SUBMITTED · PENDING · CONFIRMED ·
FAILED · REPLACED · EXPIRED.

## Platform fee (15%)

Brands pay a **15% platform fee, charged on top of the creator payout**. It is
never deducted from what a creator receives.

```
brand deposits   payout + 15% fee
creator receives payout          <- always the exact signed amount
treasury         15% fee
```

**Why this is the load-bearing rule.** A creator is promised a fixed amount for
verified, disclosed work. Deducting the fee from that amount means a creator
receives less than advertised for work they already did, and word travels fast
in creator communities. Reducing the *number of funded claims* instead leaves
every creator whole.

A $2,500 campaign at a $5 payout funds **434 posts** (434 × $5.75 = $2,495.50),
each creator paid the full $5. It does **not** fund 500 posts at $4.25.

**Where it lives**

| Piece | Location |
| --- | --- |
| `PLATFORM_FEE_BPS = 1500` | `RewardDistributor.sol` (immutable constant) |
| `PLATFORM_FEE_BPS` setting | `config/settings/base.py` (mirrors the contract) |
| `feeFor` / `requiredDeposit` | `RewardDistributor.sol` + `apps/blockchain/fees.py` |
| `FEE_ACCRUED` ledger entry | written on claim confirmation |

The brand quote is computed server-side in `apps/blockchain/fees.py` with
integer smallest-unit math that mirrors Solidity's flooring division, so a
brand is never quoted a unit more than the contract would accept.

**Solvency.** Each claim checks
`totalDeposited − totalPaid − totalFeesAccrued + totalFeesWithdrawn ≥ payout + fee`
and reverts with `InsufficientEscrow` otherwise. An under-funded escrow can
therefore never quietly pay a creator less than signed, and never consume funds
owed to other creators.

**Treasury withdrawals are bounded** by fees actually accrued
(`withdrawTreasury`, reverting `TreasuryUnderfunded`). The previous
`withdraw(uint256)` could move any token held by the contract — including
escrow still owed to creators — so an owner-key compromise drained every pending
payout. The old function was removed rather than left alongside the safe one.

**No burn.** `RewardToken` exposes `burn`/`burnFrom` for a future fee-burn, but
nothing calls them. Creators are paid in fiat, and the concrete cost to fund
today (a security audit, plus a securities opinion before any token launch) is
funded first. Revisit once treasury is healthy.

## Event listener
Listen for `RewardClaimed`, `PlatformFeeAccrued`, `Deposit`, `TreasuryWithdrawal`
and admin events. Use confirmations appropriate for the chain.

## Brand funding (USDG)

Brands pay in **USDG** and creators are paid in **USDG**. There is no fiat
conversion anywhere in the system, so the platform is not acting as an exchanger
and does not take on conversion or custody risk.

USDG is a stablecoin specifically so a creator's $5 is $5 at payout. This is why
creators are not paid in the platform token: that would expose the people doing
the work to a token's price, which is the failure mode the whole payout design
exists to avoid.

```
brand sends USDG  ->  platform holds USDG  ->  creators paid USDG
                       15% retained as fee
```

The 15% platform fee applies exactly as in the contract: charged on top of the
payout, never deducted from it. `apps/campaigns/funding.py` imports the
arithmetic from `apps/blockchain/fees.py` rather than reimplementing it, so a
quote given to a brand is identical to what `requiredDeposit` accepts on chain.

### Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET/POST /api/v1/brand/profile/` | Read or create the caller's brand |
| `GET/POST /api/v1/brand/funding/` | List deposits / record a new one |
| `POST /api/v1/brand/funding/<id>/confirm/` | Confirm a deposit on-chain |
| `POST /api/v1/brand/quote/` | Cost of a campaign, fee included |
| `GET /api/v1/brand/campaigns/` | Campaigns this brand funds |

Every endpoint is scoped to the signed-in user's own brand. Confirmation
re-checks ownership on the object rather than trusting the URL, so a brand
cannot credit another brand's deposit by guessing an id.

### What "confirmed" actually means

`POST /api/v1/brand/funding/<id>/confirm/` lets a brand *ask* whether their
money has landed. It does not let them assert that it has. The brand is the
party with an interest in the answer, so the answer is read from a receipt by
`apps/blockchain/deposits.verify_deposit`, which checks all of:

| Check | Refuses when |
| --- | --- |
| RPC reachable | The node cannot be reached — a deposit is never credited because the platform *couldn't* check it |
| Chain id | The node is not on the chain the deposit claims |
| Token allowlisted | The symbol is unknown or disabled for that chain, so its decimals cannot be trusted |
| Receipt exists | No receipt: unmined, or the hash is wrong |
| Status 0 | The transaction reverted and moved nothing |
| Confirmation depth | Fewer than `FUNDING_CONFIRMATIONS` (default 3) — a shallow transfer can still be reorged out |
| Emitting contract | The `Transfer` log did not come from the allowlisted token's own address |
| Recipient | The transfer did not go to `FUNDING_TREASURY_ADDRESS` |
| Amount | Less arrived than the deposit claims |

Every one of these leaves the deposit `PENDING` and credits nothing. There is
no `force` parameter and no unverified path.

The recipient check is what stops the obvious exploit: without it, a brand
could make a real, correctly-valued transfer of its own stablecoin to a wallet
it controls, submit that hash, and have the platform call it funding. The
treasury address comes from settings and is never caller-supplied — a check
that accepts a caller-chosen recipient is not a check.

Two of these settings are required before any deposit can be confirmed at all:

```bash
FUNDING_TREASURY_ADDRESS=0x...   # the address brands must send to
FUNDING_CONFIRMATIONS=3          # depth before a transfer counts as final
```

Leaving `FUNDING_TREASURY_ADDRESS` empty does not disable verification, it
disables crediting. That is deliberate: an unset treasury must not become a way
to confirm deposits against an address nobody checked.

Confirmation also records what it verified — block, confirmation count, sender,
and the amount actually received — on the deposit and in the audit log. A
funding dispute is settled by pointing at a block, not by asserting that a
check happened.

`confirm_pending_fundings` runs on a 2-minute beat and re-checks deposits still
pending, so a transfer that was mined but not yet deep enough is credited
without the brand having to poll.

### Two rules that protect real money

**Recording is not crediting.** A deposit is stored `PENDING` and does not
count toward a balance until confirmed against the chain. Crediting money
because a client said it arrived is just the client asserting that.

**One transfer, one credit.** `tx_hash` is unique per `(chain_id, tx_hash)` at
the database level, so a replayed or resubmitted deposit cannot inflate a
balance even if a future code path bypasses the service-level check. The
service check exists only to return a readable error; the constraint is the
actual guard.

The same hash on a *different* chain is a different transfer and is allowed.

### Payout integrity

Three rules keep the platform from promising money it does not have. Each was
a real defect found while wiring the USDG rail up.

**Decimals come from the token, never a default.** `fees.platform_fee` and
`quote_campaign_cost` take an explicit `decimals` argument. USDG is **6**
decimals while the platform default is 18, and quoting a fee at 18 invents
precision the chain does not have — a sub-cent payout would be quoted a
1.5e-8 fee the contract would never charge. `mark_claim_confirmed` and the
quote endpoint both read the precision from the `TokenConfig` allowlist.

**A campaign's payout token must be allowlisted for its chain.** A campaign
names free text, but the money a creator receives is whatever the distributor
holds. If those disagree the campaign promises a payout the contract cannot
deliver, and it only fails at claim time — after the work is done. The check
is skipped only when no allowlist exists for that chain at all (a fresh
install); it is never skipped merely because the symbol is absent, which would
defeat it entirely.

**A campaign cannot launch unfunded.** `set_campaign_status(ACTIVE)` calls
`require_campaign_funding`, which requires the brand's *confirmed* USDG to
cover `budget × 1.15`. A PENDING deposit does not count: recording a deposit
is not crediting it. Without this, creators post, verification approves the
work, and the payout then fails — the exact failure the funding model exists
to prevent.

Staff-funded campaigns (`funding_brand` null) skip the check so seed and
development campaigns still launch. Brands may create and launch their own
campaigns; the funding gate, not a staff-only permission, is what stops an
unfunded one going live.

### Registering the payout token

The token allowlist is what `Campaign.token_symbol` is checked against, so a
campaign cannot pay in a token the distributor does not hold. There is no
management command yet — register via Django admin at `/admin/` (TokenConfig),
or from a shell:

```bash
python manage.py shell -c "
from apps.blockchain.models import TokenConfig
TokenConfig.objects.get_or_create(
    symbol='USDG', chain_id=46630,
    defaults={'address': '<TESTNET ADDRESS>', 'decimals': 18, 'enabled': True})"
```

### ⚠️ Robinhood Chain does not document a USDG contract

Checked against the chain on 2026-09-27. Robinhood Chain's documented token
contracts are **WETH** and **USDG** (Global Dollar). No USDG contract is
listed, and the USDG address published in the docs returns **no contract code**
on testnet (`eth_getCode` → `0x`), which is expected because that address is a
mainnet address.

So the USDG rail this build assumes cannot be enabled as written. Before going
further, pick one:

| Option | Consequence |
| --- | --- |
| **Use USDG** | Aligns with the chain. USDG is Paxos's Global Dollar, a dollar stablecoin, so the "no volatility for creators" property holds |
| **Find the real testnet USDG address** | If Robinhood has since deployed one. Must be verified on-chain (`eth_getCode` non-empty, `decimals()` = 6), not copied from a docs page |
| **Deploy test USDG yourself** | Only for local testing; never for real payouts |

**Verify any address on-chain before registering it.** A wrong or empty address
on the allowlist means a campaign that passes validation but cannot pay:

```python
from web3 import Web3
w3 = Web3(Web3.HTTPProvider('https://rpc.testnet.chain.robinhood.com'))
addr = Web3.to_checksum_address('<ADDRESS>')
assert len(w3.eth.get_code(addr)) > 2, 'no contract at this address'
print('decimals =', w3.eth.call({'to': addr, 'data': '0x313ce567'}).hex())
```

`decimals()` must match what you register. Getting this wrong is exactly the
class of bug the decimals fix addressed — a quote computed at the wrong
precision is a quote the chain will not honour.

## Treasury
Admin treasury separated from app wallets. Multisig for meaningful balances.
No keys in source code; secure signing system in production. Don't hold user
funds unnecessarily. Set `TREASURY_ADDRESS` to a multisig on mainnet so the
deployer key is not also the fee withdrawal key.

## Token support
Per campaign: chain ID, token contract address, symbol, decimals, reward
token, minimum/maximum claim. Validate token contracts against an allowlist.

## Accounting
Internal ledger: reward earned, approved, claimed, transaction hash, token,
amount in smallest unit, timestamp. **Blockchain balance ≠ internal ledger** —
reconcile them.

## Security & emergency controls
Contracts get static analysis, unit tests, integration tests, testnet
testing, independent security review before significant funds. Emergency:
pause claiming, disable a token, disable a campaign, revoke/rotate claim
signer, monitor unusual claim volume. Admin actions logged.

## Frontend wallet UX
Show wallet `0x1234...ABCD`, network, available/claimable tokens. Claim button
shows: amount, token, network, estimated gas if available, destination wallet,
confirmation state. No promises of instant settlement before confirmation.

## Legal/risk
Obtain legal advice before production on: token rewards, promotions,
securities/financial regulation, money transmission, consumer protection,
tax reporting, sanctions/AML obligations.