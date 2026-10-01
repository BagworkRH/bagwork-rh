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
  const PLATFORM_FEE_BPS = 1500n; // 15%

  async function deployFixture() {
    const [deployer, seller, brand, treasuryWallet] = await ethers.getSigners();
    const RewardToken = await ethers.getContractFactory("RewardToken");
    const token = await RewardToken.deploy();
    await token.waitForDeployment();

    const RewardDistributor = await ethers.getContractFactory("RewardDistributor");
    const distributor = await RewardDistributor.deploy(
      await token.getAddress(),
      deployer.address,
      treasuryWallet.address
    );
    await distributor.waitForDeployment();

    // Fund the distributor as a brand would: deposit via the escrow so the
    // accounting (totalDeposited) is exercised, not just a raw transfer.
    const budget = ethers.parseEther("1000");
    await token.mint(deployer.address, budget);
    await token.connect(deployer).approve(await distributor.getAddress(), budget);
    await distributor.deposit(budget);

    return { token, distributor, deployer, seller, brand, treasuryWallet };
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
      name: "bagworkRH",
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

  // ------------------------------------------------------------------------ //
  // Platform fee (15%): the fee comes out of escrow, never out of a payout.
  // ------------------------------------------------------------------------ //
  describe("platform fee", function () {
    it("pays the creator the exact signed amount and withholds 15% as fee", async function () {
      const { token, distributor, deployer, seller, treasuryWallet } = await loadFixture(deployFixture);
      const amount = ethers.parseEther("5");
      const expectedFee = (amount * PLATFORM_FEE_BPS) / 10000n;
      const rewardId = 100n;
      const nonce = 100n;
      const deadline = BigInt(Math.floor(Date.now() / 1000) + 3600);

      const signature = await signClaim(
        deployer, await distributor.getAddress(), await distributor.rewardToken(),
        seller.address, rewardId, amount, nonce, deadline, BigInt(31337)
      );

      const sellerBefore = await token.balanceOf(seller.address);
      const contractBefore = await token.balanceOf(await distributor.getAddress());

      await expect(
        distributor.connect(seller).claim(rewardId, seller.address, amount, nonce, deadline, signature)
      )
        .to.emit(distributor, "RewardClaimed")
        .withArgs(rewardId, seller.address, await distributor.rewardToken(), amount, nonce)
        .and.to.emit(distributor, "PlatformFeeAccrued")
        .withArgs(rewardId, seller.address, amount, expectedFee);

      // The load-bearing assertion: the creator received the FULL signed
      // amount. A fee deducted here would be the bug the whole design avoids.
      expect(await token.balanceOf(seller.address) - sellerBefore).to.equal(amount);

      // The fee stayed in the contract: balance fell by the payout only.
      const contractAfter = await token.balanceOf(await distributor.getAddress());
      expect(contractBefore - contractAfter).to.equal(amount);

      // Treasury accounting; nothing sent to treasury yet.
      expect(await distributor.totalPaid()).to.equal(amount);
      expect(await distributor.totalFeesAccrued()).to.equal(expectedFee);
      expect(await distributor.treasuryBalance()).to.equal(expectedFee);
      expect(await token.balanceOf(treasuryWallet.address)).to.equal(0n);
    });

    it("reverts rather than underpay when escrow cannot cover payout plus fee", async function () {
      const [deployer, seller, brand, treasuryWallet] = await ethers.getSigners();
      const RewardToken = await ethers.getContractFactory("RewardToken");
      const token = await RewardToken.deploy();
      await token.waitForDeployment();
      const RewardDistributor = await ethers.getContractFactory("RewardDistributor");
      const distributor = await RewardDistributor.deploy(
        await token.getAddress(), deployer.address, treasuryWallet.address
      );
      await distributor.waitForDeployment();

      // Underfund: exactly 5 tokens deposited, but a 5-token payout needs
      // 5.75. This is the case that must NOT silently pay the creator 4.25.
      const underfunded = ethers.parseEther("5");
      await token.mint(deployer.address, underfunded);
      await token.connect(deployer).approve(await distributor.getAddress(), underfunded);
      await distributor.deposit(underfunded);

      const amount = ethers.parseEther("5");
      const rewardId = 200n;
      const nonce = 200n;
      const deadline = BigInt(Math.floor(Date.now() / 1000) + 3600);
      const signature = await signClaim(
        deployer, await distributor.getAddress(), await distributor.rewardToken(),
        seller.address, rewardId, amount, nonce, deadline, BigInt(31337)
      );

      await expect(
        distributor.connect(seller).claim(rewardId, seller.address, amount, nonce, deadline, signature)
      ).to.be.revertedWithCustomError(distributor, "InsufficientEscrow");

      // Creator received nothing — no silent partial payment.
      expect(await token.balanceOf(seller.address)).to.equal(0n);
      expect(await distributor.totalPaid()).to.equal(0n);
      expect(await distributor.totalFeesAccrued()).to.equal(0n);
      // A rejected claim must not be marked claimed, or funds would be stuck.
      expect(await distributor.claimed(rewardId)).to.equal(false);
    });

    it("funds exactly the payouts a budget covers, with no shortfall", async function () {
      const { distributor } = await loadFixture(deployFixture);
      const payout = ethers.parseEther("5");
      const expectedFee = (payout * PLATFORM_FEE_BPS) / 10000n; // 0.75
      expect(await distributor.feeFor(payout)).to.equal(expectedFee);
      expect(await distributor.requiredDeposit(payout)).to.equal(ethers.parseEther("5.75"));

      // The documented $2,500 / $5-per-post case: a brand's budget buys
      // FEWER posts, never a smaller payout per post.
      const budget = ethers.parseEther("2500");
      const perPost = await distributor.requiredDeposit(payout);
      const postsFunded = budget / perPost; // integer division
      expect(postsFunded).to.equal(434n);
      const payouts = postsFunded * payout;
      const fees = postsFunded * expectedFee;
      expect(payouts + fees).to.be.lessThanOrEqual(budget);
      // Each creator is paid the full $5; the 15% is the brand's extra cost.
      expect(payouts).to.equal(ethers.parseEther("2170"));
    });

    it("accumulates fees across many claims and pays them to treasury on demand", async function () {
      const { token, distributor, deployer, seller, treasuryWallet } = await loadFixture(deployFixture);
      const amount = ethers.parseEther("5");
      const expectedFee = (amount * PLATFORM_FEE_BPS) / 10000n;
      const deadline = BigInt(Math.floor(Date.now() / 1000) + 3600);

      let totalFees = 0n;
      for (let i = 0; i < 3; i++) {
        const rewardId = 300n + BigInt(i);
        const nonce = 300n + BigInt(i);
        const signature = await signClaim(
          deployer, await distributor.getAddress(), await distributor.rewardToken(),
          seller.address, rewardId, amount, nonce, deadline, BigInt(31337)
        );
        await distributor.connect(seller).claim(rewardId, seller.address, amount, nonce, deadline, signature);
        totalFees += expectedFee;
      }

      expect(await distributor.totalPaid()).to.equal(amount * 3n);
      expect(await distributor.totalFeesAccrued()).to.equal(totalFees);

      const treasuryBefore = await token.balanceOf(treasuryWallet.address);
      await distributor.withdrawTreasury(totalFees);
      expect(await token.balanceOf(treasuryWallet.address) - treasuryBefore).to.equal(totalFees);
      expect(await distributor.treasuryBalance()).to.equal(0n);
    });

    it("refuses to withdraw more than accrued fees (cannot raid creator escrow)", async function () {
      const { distributor, deployer, seller } = await loadFixture(deployFixture);
      // Only fees accrued so far may be withdrawn — never the escrow owed to
      // creators. A prior `withdraw(uint256)` allowed draining pending payouts.
      await expect(distributor.withdrawTreasury(ethers.parseEther("1")))
        .to.be.revertedWithCustomError(distributor, "TreasuryUnderfunded");
    });

    it("keeps treasury withdrawals bounded to accrued fees even after claims", async function () {
      const { distributor, deployer, seller } = await loadFixture(deployFixture);
      const amount = ethers.parseEther("5");
      const expectedFee = (amount * PLATFORM_FEE_BPS) / 10000n;
      const rewardId = 400n;
      const nonce = 400n;
      const deadline = BigInt(Math.floor(Date.now() / 1000) + 3600);
      const signature = await signClaim(
        deployer, await distributor.getAddress(), await distributor.rewardToken(),
        seller.address, rewardId, amount, nonce, deadline, BigInt(31337)
      );
      await distributor.connect(seller).claim(rewardId, seller.address, amount, nonce, deadline, signature);

      // One wei more than accrued must fail.
      await expect(distributor.withdrawTreasury(expectedFee + 1n))
        .to.be.revertedWithCustomError(distributor, "TreasuryUnderfunded");
      // Exactly accrued succeeds.
      await distributor.withdrawTreasury(expectedFee);
      expect(await distributor.treasuryBalance()).to.equal(0n);
    });
  });

  // ------------------------------------------------------------------------ //
  // Token supply cap
  // ------------------------------------------------------------------------ //
  describe("RewardToken supply cap", function () {
    it("refuses to mint above the hard cap", async function () {
      const [deployer] = await ethers.getSigners();
      const RewardToken = await ethers.getContractFactory("RewardToken");
      const token = await RewardToken.deploy();
      await token.waitForDeployment();
      const maxSupply = await token.MAX_SUPPLY();
      // Matches pons' fixed launch supply of 1,000,000,000.
      expect(maxSupply).to.equal(ethers.parseEther("1000000000"));

      await token.mint(deployer.address, maxSupply);
      expect(await token.totalSupply()).to.equal(maxSupply);
      // One wei over the cap reverts rather than minting a partial amount.
      await expect(token.mint(deployer.address, 1n))
        .to.be.revertedWithCustomError(token, "CapExceeded");
    });
  });
});