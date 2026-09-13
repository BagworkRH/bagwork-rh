import { ethers, network } from "hardhat";

/**
 * Deploys the RewardDistributor and mintable test RewardToken.
 * Usage: npx hardhat run scripts/deploy.ts --network sepolia
 * Set DEPLOYER_PRIVATE_KEY in the environment. Never hard-code credentials.
 */
async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying contracts with account:", deployer.address);
  console.log("Network:", network.name);

  const RewardToken = await ethers.getContractFactory("RewardToken");
  const token = await RewardToken.deploy();
  await token.waitForDeployment();
  console.log("RewardToken deployed to:", await token.getAddress());

  const RewardDistributor = await ethers.getContractFactory("RewardDistributor");
  const distributor = await RewardDistributor.deploy(await token.getAddress(), deployer.address);
  await distributor.waitForDeployment();
  console.log("RewardDistributor deployed to:", await distributor.getAddress());
  console.log("Signer:", deployer.address);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});