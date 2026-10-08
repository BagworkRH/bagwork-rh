import { ethers, network } from "hardhat";
import * as fs from "fs";

/**
 * Submit a prepared claim authorization on-chain (Stage 6 rehearsal).
 *
 * Reads the authorization JSON that `manage.py prepare_claim` writes and sends
 * its calldata from the claim's own wallet. The contract requires
 * `msg.sender == wallet`, and the submission is the wallet's responsibility in
 * production too (the backend only signs), so this runs with the wallet's key —
 * never the backend's.
 *
 * Usage:
 *   CLAIM_FILE=claim-authorization.json SUBMITTER_PRIVATE_KEY=0x... \
 *     npx hardhat run scripts/submit-claim.ts --network robinhoodTestnet
 *   # or: npm run submit:claim:testnet   (with the two vars set in .env)
 */
async function main() {
  const claimFile = (process.env.CLAIM_FILE || "").trim();
  if (!claimFile) throw new Error("Set CLAIM_FILE to the authorization JSON path.");

  const key = (process.env.SUBMITTER_PRIVATE_KEY || "").trim();
  if (!key) throw new Error("Set SUBMITTER_PRIVATE_KEY (the claiming wallet's key).");

  if (!fs.existsSync(claimFile)) {
    throw new Error(`Claim file not found: ${claimFile} (run prepare_claim first).`);
  }
  const payload = JSON.parse(fs.readFileSync(claimFile, "utf8"));

  const wallet = new ethers.Wallet(key, ethers.provider);
  // The contract checks msg.sender == the authorized wallet; submitting from any
  // other address reverts. Fail here with a clear message instead.
  if (wallet.address.toLowerCase() !== String(payload.wallet).toLowerCase()) {
    throw new Error(
      `Signer ${wallet.address} is not the claim wallet ${payload.wallet}. ` +
        `The reward is paid to ${payload.wallet}, so that wallet must submit.`,
    );
  }

  console.log("Network:   ", network.name);
  console.log("Claim:     ", payload.claim_id);
  console.log("Reward id: ", payload.reward_id);
  console.log("Amount:    ", payload.amount, payload.token_symbol);
  console.log("To wallet: ", payload.wallet);
  console.log("Contract:  ", payload.transaction.to);

  console.log("Sending claim transaction…");
  const tx = await wallet.sendTransaction({
    to: payload.transaction.to,
    data: payload.transaction.data,
    value: payload.transaction.value || "0x0",
  });
  console.log("tx hash:", tx.hash);
  const receipt = await tx.wait();
  console.log("status: ", receipt?.status === 1 ? "success" : "reverted");

  const explorer = "https://explorer.testnet.chain.robinhood.com";
  console.log(`\nExplorer: ${explorer}/tx/${tx.hash}`);
  console.log(`Claim id ${payload.claim_id} submitted. Reconcile the backend to mark it CONFIRMED.`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
