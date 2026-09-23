import { expect } from "chai";
import { ethers } from "hardhat";
import { loadFixture } from "@nomicfoundation/hardhat-toolbox/network-helpers";
import { Signer } from "ethers";

/**
 * RewardDistributor tests (Spec 04).
 *
 * Covered here: signature verification, claim authorization, replay
 * protection, and emergency pause. Full chain integration (listener,
 * reconciliation) is covered by backend tests and the Phase 6 deployment.
 */
describe("RewardDistributor", function () {
  async function deployFixture() {
    const [deployer, seller] = await ethers.getSigners();
    const RewardToken = await ethers.getContractFactory("RewardToken");
    const token = await RewardToken.deploy();
    await token.waitForDeployment();

    const RewardDistributor = await ethers.getContractFactory("RewardDistributor");
    const distributor = await RewardDistributor.deploy(
      await token.getAddress(),
      deployer.address
    );
    await distributor.waitForDeployment();

    // Fund the distributor with reward tokens.
    const budget = ethers.parseEther("1000");
    await token.mint(deployer.address, budget);
    await token.transfer(await distributor.getAddress(), budget);

    return { token, distributor, deployer, seller };
  }

  async function signClaim(
    signer: Signer,
    contractAddress: string,
    tokenAddress: string,
    wallet: string,
    rewardId: bigint,
    amount: bigint,
    nonce: bigint,
    deadline: bigint,
    chainId: bigint
  ): Promise<string> {
    const domain = {
      name: "CryptoRewards",
      version: "1",
      chainId: Number(chainId),
      verifyingContract: contractAddress,
    };
    const types = {
      Claim: [
        { name: "wallet", type: "address" },
        { name: "rewardId", type: "uint256" },
        { name: "token", type: "address" },
        { name: "amount", type: "uint256" },
        { name: "nonce", type: "uint256" },
        { name: "deadline", type: "uint256" },
        { name: "chainId", type: "uint256" },
      ],
    };
    const value = { wallet, rewardId, token: tokenAddress, amount, nonce, deadline, chainId };
    return signer.signTypedData(domain, types, value);
  }

  it("rejects claims from expired authorizations", async function () {
    const { distributor, deployer, seller } = await loadFixture(deployFixture);
    const rewardId = 1n;
    const amount = ethers.parseEther("5");
    const nonce = 1n;
    const chainId = BigInt(31337);

    // Use the chain's own clock: wall-clock time can drift from EVM time.
    const latest = await ethers.provider.getBlock("latest");
    const deadline = BigInt(latest!.timestamp - 60); // already expired
    const signature = await signClaim(
      deployer, await distributor.getAddress(), await distributor.rewardToken(),
      seller.address, rewardId, amount, nonce, deadline, chainId
    );
    await expect(
      distributor.connect(seller).claim(rewardId, seller.address, amount, nonce, deadline, signature)
    ).to.be.revertedWithCustomError(distributor, "ClaimExpired");
  });

  it("rejects unauthorized (wrong signer) claims", async function () {
    const { distributor, deployer, seller } = await loadFixture(deployFixture);
    const rewardId = 1n;
    const amount = ethers.parseEther("5");
    const nonce = 1n;
    const chainId = BigInt(31337);
    const deadline = BigInt(Math.floor(Date.now() / 1000) + 3600);
    const signature = await signClaim(
      seller, await distributor.getAddress(), await distributor.rewardToken(),
      seller.address, rewardId, amount, nonce, deadline, chainId
    );
    await expect(
      distributor.connect(seller).claim(rewardId, seller.address, amount, nonce, deadline, signature)
    ).to.be.revertedWithCustomError(distributor, "InvalidSignature");
  });

  it("processes a valid claim and records it as claimed (replay protection)", async function () {
    const { distributor, deployer, seller } = await loadFixture(deployFixture);
    const rewardId = 1n;
    const amount = ethers.parseEther("5");
    const nonce = 1n;
    const chainId = BigInt(31337);
    const deadline = BigInt(Math.floor(Date.now() / 1000) + 3600);
    const signature = await signClaim(
      deployer, await distributor.getAddress(), await distributor.rewardToken(),
      seller.address, rewardId, amount, nonce, deadline, chainId
    );

    await expect(
      distributor.connect(seller).claim(rewardId, seller.address, amount, nonce, deadline, signature)
    )
      .to.emit(distributor, "RewardClaimed")
      .withArgs(rewardId, seller.address, await distributor.rewardToken(), amount, nonce);

    expect(await distributor.claimed(rewardId)).to.equal(true);

    // Replay must fail.
    await expect(
      distributor.connect(seller).claim(rewardId, seller.address, amount, nonce, deadline, signature)
    ).to.be.revertedWithCustomError(distributor, "ClaimAlreadyProcessed");
  });

  it("pauses claiming in emergencies", async function () {
    const { distributor, deployer, seller } = await loadFixture(deployFixture);
    await distributor.setClaimingPaused(true);

    const rewardId = 2n;
    const amount = ethers.parseEther("1");
    const deadline = BigInt(Math.floor(Date.now() / 1000) + 3600);
    const signature = await signClaim(
      deployer, await distributor.getAddress(), await distributor.rewardToken(),
      seller.address, rewardId, amount, 2n, deadline, BigInt(31337)
    );
    await expect(
      distributor.connect(seller).claim(rewardId, seller.address, amount, 2n, deadline, signature)
    ).to.be.revertedWithCustomError(distributor, "ClaimPaused");
  });
});