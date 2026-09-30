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
> ending 29 September 2026. Unverified against official docs — check before
> budgeting, though it barely moves the number.

Generate a **fresh, dedicated** key. Never reuse a key that has touched
mainnet for anything else, and never commit it.