import { ethers, network } from "hardhat";

/**
 * Send the payout token (USDG) from one wallet to another — the brand's leg of
 * the funding rail (Stage 6).
 *
 * The platform never moves a brand's money: the brand sends the stablecoin
 * itself, records the hash, and verification reads the receipt. This script
 * stands in for the brand's wallet during the funding rehearsal.
 *
 * Usage:
 *   USDG_FROM_KEY=0x... USDG_TO=0x... USDG_AMOUNT=5 \
 *     npx hardhat run scripts/send-usdg.ts --network robinhoodTestnet
 *   # or: npm run send:usdg:testnet   (with the three vars in .env)
 */
const ERC20_ABI = [
  "function symbol() view returns (string)",
  "function decimals() view returns (uint8)",
  "function balanceOf(address) view returns (uint256)",
  "function transfer(address to, uint256 amount) returns (bool)",
];

async function main() {
  const tokenAddress = (process.env.PAYOUT_TOKEN_ADDRESS || "").trim();
  const key = (process.env.USDG_FROM_KEY || "").trim();
  const to = (process.env.USDG_TO || "").trim();
  const amount = (process.env.USDG_AMOUNT || "").trim();
  if (!tokenAddress) throw new Error("Set PAYOUT_TOKEN_ADDRESS (the USDG token).");
  if (!key) throw new Error("Set USDG_FROM_KEY (the sending wallet's key).");
  if (!to) throw new Error("Set USDG_TO (the recipient — e.g. FUNDING_TREASURY_ADDRESS).");
  if (!amount) throw new Error('Set USDG_AMOUNT (whole tokens, e.g. "5").');

  const wallet = new ethers.Wallet(key, ethers.provider);
  const token = new ethers.Contract(ethers.getAddress(tokenAddress), ERC20_ABI, wallet);

  const [symbol, decimals, balance, recipient] = await Promise.all([
    token.symbol(),
    token.decimals(),
    token.balanceOf(wallet.address),
    ethers.getAddress(to),
  ]);
  const raw = ethers.parseUnits(amount, Number(decimals));

  console.log("Network:  ", network.name);
  console.log("From:     ", wallet.address);
  console.log("To:       ", recipient);
  console.log("Token:    ", `${symbol} (${tokenAddress}, ${Number(decimals)} decimals)`);
  console.log("Balance:  ", ethers.formatUnits(balance, Number(decimals)), symbol);
  console.log("Sending:  ", amount, symbol);

  if (balance < raw) {
    throw new Error(`Insufficient ${symbol}: have ${ethers.formatUnits(balance, Number(decimals))}.`);
  }

  const tx = await token.transfer(recipient, raw);
  console.log("tx hash:  ", tx.hash);
  const receipt = await tx.wait();
  console.log("status:   ", receipt?.status === 1 ? "success" : "reverted");
  console.log(`\nRecord this hash as the brand deposit:\n    ${tx.hash}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
