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

// The token the distributor pays creators in. When set, the distributor is
// wired to this existing token (the USDG rail: brands fund USDG and creators
// are paid USDG) instead of a freshly deployed dev RewardToken. Read-only
// metadata is used to confirm it is a real ERC-20 and to echo the decimals the
// backend must register; nothing here transfers it.
const EXTERNAL_TOKEN = (process.env.PAYOUT_TOKEN_ADDRESS || "").trim();

const ERC20_METADATA_ABI = [
  "function symbol() view returns (string)",
  "function decimals() view returns (uint8)",
];

/**
 * Resolve the payout token for the distributor.
 *
 * Two rails exist. The development rail deploys the mintable RewardToken and
 * pays in it. The production rail pays in the token brands actually fund with
 * (USDG), whose address is supplied via PAYOUT_TOKEN_ADDRESS — the contract
 * already exists and is not ours to deploy. Confirming it is a real ERC-20 here
 * means a typo fails the deploy instead of producing a distributor that can
 * never pay a creator.
 */
async function resolvePayoutToken(chainId: bigint): Promise<string> {
  if (!EXTERNAL_TOKEN) {
    const RewardToken = await ethers.getContractFactory("RewardToken");
    const token = await RewardToken.deploy();
    await token.waitForDeployment();
    const address = await token.getAddress();
    console.log("Payout token: dev RewardToken (mintable) deployed to", address);
    return address;
  }

  let address: string;
  try {
    address = ethers.getAddress(EXTERNAL_TOKEN); // checksums, throws if malformed
  } catch {
    throw new Error(`PAYOUT_TOKEN_ADDRESS is not a valid address: ${EXTERNAL_TOKEN}`);
  }

  const code = await ethers.provider.getCode(address);
  if (code === "0x") {
    throw new Error(
      `No contract at PAYOUT_TOKEN_ADDRESS ${address} on chain ${chainId}. ` +
        `A distributor wired to an address with no code could never pay a claim.`,
    );
  }

  const token = new ethers.Contract(address, ERC20_METADATA_ABI, ethers.provider);
  let symbol = "(symbol() reverted)";
  try {
    symbol = await token.symbol();
  } catch {
    // Not fatal: some proxies revert on the symbol. The address and code check
    // above are what matter; the operator registers the real symbol from the
    // token's own docs.
  }
  const decimals = await token.decimals();
  console.log(`Payout token: ${symbol} at ${address} (decimals ${decimals})`);
  console.log(
    "Register it for the backend before launching a campaign paying in it:\n" +
      `    TokenConfig(symbol="${symbol}", chain_id=${chainId}, address="${address}", decimals=${decimals})`,
  );
  return address;
}

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

  const tokenAddress = await resolvePayoutToken(chainId);

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
  console.log(`REWARD_TOKEN_ADDRESS=${tokenAddress}   # the token the distributor pays`);
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