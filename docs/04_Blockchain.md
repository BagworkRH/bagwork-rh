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

## Event listener
Listen for `RewardClaimed`, `Deposit`, withdrawal/admin events. Use
confirmations appropriate for the chain.

## Treasury
Admin treasury separated from app wallets. Multisig for meaningful balances.
No keys in source code; secure signing system in production. Don't hold user
funds unnecessarily.

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