import { ethers, network } from "hardhat";

/**
 * Fund the RewardDistributor's escrow with the payout token.
 *
 * Claims are paid from the distributor's own escrow, not from the funding
 * treasury EOA: `claim()` checks `totalDeposited - totalPaid - fees >= payout
 * + fee` and reverts with InsufficientEscrow otherwise. So before a creator can
 * be paid, the owner must `approve` the distributor and `deposit` the token.
 *
 * Usage:
 *   DISTRIBUTOR_ADDRESS=0x... ESCROW_DEPOSIT=50 \
 *     npx hardhat run scripts/fund-escrow.ts --network robinhoodTestnet
 *   # or: npm run fund:escrow:testnet   (with the two vars set in .env)
 *
 * The amount is a whole-token figure (e.g. "50" = 50 USDG); decimals are read
 * from the token, never assumed.
 */
const ERC20_ABI = [
  "function symbol() view returns (string)",
  "function decimals() view returns (uint8)",
  "function balanceOf(address) view returns (uint256)",
  "function approve(address spender, uint256 amount) returns (bool)",
];

const DISTRIBUTOR_ABI = [
  "function rewardToken() view returns (address)",
  "function deposit(uint256 amount)",
  "function spendableEscrow() view returns (uint256)",
];

async function main() {
  const distributorAddress = (
    process.env.DISTRIBUTOR_ADDRESS ||
    process.env.CONTRACT_ADDRESS ||
    ""
  ).trim();
  if (!distributorAddress) {
    throw new Error("Set DISTRIBUTOR_ADDRESS (the deployed RewardDistributor).");
  }
  const amount = (process.env.ESCROW_DEPOSIT || "").trim();
  if (!amount) {
    throw new Error('Set ESCROW_DEPOSIT (a whole-token amount, e.g. "50").');
  }

  const [owner] = await ethers.getSigners();
  if (!owner) throw new Error("No signer. Set DEPLOYER_PRIVATE_KEY in the environment.");

  const distributor = new ethers.Contract(
    ethers.getAddress(distributorAddress),
    DISTRIBUTOR_ABI,
    owner,
  );
  // Read the payout token from the contract rather than trusting an env var, so
  // the deposit cannot be made in a token the distributor will never pay.
  const tokenAddress = await distributor.rewardToken();
  const token = new ethers.Contract(tokenAddress, ERC20_ABI, owner);

  const [symbol, decimalsRaw, balance] = await Promise.all([
    token.symbol(),
    token.decimals(),
    token.balanceOf(owner.address),
  ]);
  const decimals = Number(decimalsRaw);
  const raw = ethers.parseUnits(amount, decimals);

  console.log("Network:   ", network.name);
  console.log("Owner:     ", owner.address);
  console.log("Distributor:", ethers.getAddress(distributorAddress));
  console.log("Token:     ", `${symbol} (${tokenAddress}, ${decimals} decimals)`);
  console.log("Balance:   ", ethers.formatUnits(balance, decimals), symbol);
  console.log("Depositing:", amount, symbol);

  if (balance < raw) {
    throw new Error(
      `Insufficient ${symbol}: have ${ethers.formatUnits(balance, decimals)}, need ${amount}.`,
    );
  }

  console.log("Approving the distributor…");
  const approveTx = await token.approve(ethers.getAddress(distributorAddress), raw);
  await approveTx.wait();

  console.log("Depositing into escrow…");
  const depositTx = await distributor.deposit(raw);
  await depositTx.wait();

  const escrow = await distributor.spendableEscrow();
  console.log("Escrow now:", ethers.formatUnits(escrow, decimals), symbol);
  console.log("\nThe distributor can now pay claims from this escrow.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
