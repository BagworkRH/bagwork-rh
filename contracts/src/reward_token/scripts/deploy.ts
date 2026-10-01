import { ethers, network } from "hardhat";

/**
 * Deploys the RewardDistributor and mintable test RewardToken.
 *
 * Usage:
 *   npx hardhat run scripts/deploy.ts --network robinhoodTestnet
 *   npx hardhat run scripts/deploy.ts --network robinhood        # mainnet
 *   npx hardhat run scripts/deploy.ts --network sepolia          # legacy
 *
 * Set DEPLOYER_PRIVATE_KEY in the environment. Never hard-code credentials.
 *
 * The EIP-712 domain name is baked into the constructor's DOMAIN_SEPARATOR and
 * must match the backend exactly (apps/blockchain/signing.py DOMAIN_NAME).
 * The expected value is read from EIP712_DOMAIN_NAME so a mismatch fails the
 * deploy rather than silently producing signatures the backend rejects.
 */
const EXPECTED_DOMAIN_NAME = process.env.EIP712_DOMAIN_NAME || "bagworkRH";

function domainSeparatorSource(): string | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    return require("fs").readFileSync(
      "contracts/RewardDistributor.sol",
      "utf8",
    ) as string;
  } catch {
    return null;
  }
}

async function main() {
  // Check the domain BEFORE touching signers: with no DEPLOYER_PRIVATE_KEY the
  // network has no accounts and the signer lookup would throw first, masking
  // the real problem.
  const source = domainSeparatorSource();
  if (source && !source.includes(`keccak256("${EXPECTED_DOMAIN_NAME}")`)) {
    throw new Error(
      `EIP-712 domain mismatch: RewardDistributor.sol does not contain ` +
        `keccak256("${EXPECTED_DOMAIN_NAME}"). Refusing to deploy — signatures ` +
        `would be rejected by the backend.`,
    );
  }

  const [deployer] = await ethers.getSigners();
  if (!deployer) {
    throw new Error(
      "No signer available. Set DEPLOYER_PRIVATE_KEY in the environment.",
    );
  }
  console.log("Deploying contracts with account:", deployer.address);

  // Treasury must be a multisig in production, never the deployer EOA, so a
  // compromised deployer key cannot also control the fee money.
  const treasuryAddress = process.env.TREASURY_ADDRESS || deployer.address;
  if (!process.env.TREASURY_ADDRESS) {
    console.warn(
      "WARNING: TREASURY_ADDRESS unset — fees will be sent to the deployer EOA.\n" +
        "         Set TREASURY_ADDRESS to a multisig before mainnet.",
    );
  }
  console.log("Network:", network.name);
  const chainId = (await ethers.provider.getNetwork()).chainId;
  console.log("Chain ID:", chainId.toString());

  const RewardToken = await ethers.getContractFactory("RewardToken");
  const token = await RewardToken.deploy();
  await token.waitForDeployment();
  const tokenAddress = await token.getAddress();
  console.log("RewardToken deployed to:", tokenAddress);

  const RewardDistributor = await ethers.getContractFactory("RewardDistributor");
  const distributor = await RewardDistributor.deploy(
    tokenAddress,
    deployer.address,
    treasuryAddress,
  );
  await distributor.waitForDeployment();
  const distributorAddress = await distributor.getAddress();
  console.log("RewardDistributor deployed to:", distributorAddress);
  console.log("Signer:", deployer.address);
  console.log("Treasury:", treasuryAddress);

  // Surface the fee economics at deploy time so the deployed numbers are never
  // a surprise for the first brand or creator.
  const bps = await distributor.PLATFORM_FEE_BPS();
  console.log(`Platform fee: ${bps.toString()} bps (${Number(bps) / 100}%)`);

  // Read back the on-chain domain separator so it can be cross-checked against
  // the backend's build_domain_separator() for this chain id and address.
  const onChainSeparator: string = await distributor.DOMAIN_SEPARATOR();
  console.log("DOMAIN_SEPARATOR:", onChainSeparator);

  console.log("\n--- Set these in the backend environment ---");
  console.log(`CHAIN_ID=${chainId.toString()}`);
  console.log(`REWARD_TOKEN_ADDRESS=${tokenAddress}`);
  console.log(`CONTRACT_ADDRESS=${distributorAddress}`);
  console.log(`CLAIM_SIGNER_ADDRESS=${deployer.address}`);
  console.log(`TREASURY_ADDRESS=${treasuryAddress}`);
  console.log(`CLAIM_SIGNER=<the private key for ${deployer.address}>`);
  console.log(
    "\nFunding model: a brand deposits payout + 15% fee per claim. Creators are " +
      "paid the full signed payout in fiat; fees accrue to treasury.",
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});