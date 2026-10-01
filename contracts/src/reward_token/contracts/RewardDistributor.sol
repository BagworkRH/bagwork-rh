// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

/**
 * @title RewardDistributor
 * @notice Minimal reward distributor for the Crypto Rewards platform (Spec 04).
 *
 * The off-chain system calculates an approved reward and signs an
 * authorization message. The seller submits a claim transaction; the contract
 * verifies the authorization (signer, wallet, reward id, token, amount,
 * nonce, expiry, chain id) and prevents replay. Tokens are held in this
 * contract and released only to the authorized claimant.
 *
 * PLATFORM FEE (15%)
 * --------------------
 * Brands pay a 15% platform fee. That fee is charged ON TOP of the creator
 * payout and is taken from escrow at claim time. It is NEVER deducted from the
 * signed `amount`:
 *
 *     brand deposits   payout + fee
 *     creator receives payout   (exactly the signed amount, always)
 *     treasury keeps   fee
 *
 * This is the load-bearing rule of the product. A creator is promised a fixed
 * amount for verified work; a fee taken out of that amount means a creator
 * receives less than advertised for work they already did. Reducing the number
 * of funded claims instead leaves every creator whole.
 *
 * Solvency is enforced per claim: escrow must cover payout + fee, so an
 * under-funded escrow can never silently consume funds owed to creators or
 * quietly pay a creator less than signed.
 *
 * NOTE: To be used only after independent security review/audit, and only on
 * testnet initially. No production funds until review is complete.
 */
contract RewardDistributor is Ownable, ReentrancyGuard {
    using ECDSA for bytes32;

    /// EIP-712 domain separator for replay protection across chains.
    bytes32 public immutable DOMAIN_SEPARATOR;
    bytes32 public constant CLAIM_TYPEHASH =
        keccak256(
            "Claim(address wallet,uint256 rewardId,address token,uint256 amount,uint256 nonce,uint256 deadline,uint256 chainId)"
        );

    IERC20 public immutable rewardToken;
    address public signer;

    /// @notice Platform fee in basis points (15% = 1500 bps).
    /// @dev Charged ON TOP of the creator payout, never deducted from it.
    uint256 public constant PLATFORM_FEE_BPS = 1500;
    uint256 private constant BPS_DENOMINATOR = 10_000;

    // --- Escrow accounting -------------------------------------------------
    // All figures are token smallest units. The invariant held at all times:
    //     spendable = totalDeposited - totalPaid - totalFeesAccrued
    //                      + totalFeesWithdrawn            >= payout + fee
    // Tracking fees separately (instead of inferring them from the token
    // balance) is what makes it impossible for a treasury withdrawal to be
    // funded out of money owed to creators.
    /// @notice Cumulative deposits received from brands.
    uint256 public totalDeposited;
    /// @notice Cumulative amounts actually paid out to creators.
    uint256 public totalPaid;
    /// @notice Cumulative platform fees withheld into treasury.
    uint256 public totalFeesAccrued;
    /// @notice Cumulative fees withdrawn from treasury.
    uint256 public totalFeesWithdrawn;

    /// @notice Destination for accumulated platform fees (multisig in production).
    address public treasury;

    /// Emitted when rewards are deposited into the escrow.
    event Deposit(address indexed token, uint256 amount);
    /// Emitted when a seller successfully claims a reward.
    event RewardClaimed(
        uint256 indexed rewardId,
        address indexed wallet,
        address indexed token,
        uint256 amount,
        uint256 nonce
    );
    /// @notice Emitted with the platform fee withheld on each claim. `payout` is
    /// what the creator received; `fee` is what the brand additionally paid.
    event PlatformFeeAccrued(
        uint256 indexed rewardId,
        address indexed wallet,
        uint256 payout,
        uint256 fee
    );
    /// @notice Emitted when fees move from treasury to the fee recipient.
    event TreasuryWithdrawal(address indexed to, uint256 amount);
    /// @notice Emitted when the treasury recipient changes.
    event TreasuryChanged(address indexed oldTreasury, address indexed newTreasury);

    /// Emitted when the authorization signer changes.
    event SignerChanged(address indexed oldSigner, address indexed newSigner);
    /// Emitted when claiming is paused/unpaused.
    event ClaimingPaused(bool paused);

    bool public claimingPaused;

    /// rewardId -> claimed (replay protection)
    mapping(uint256 => bool) public claimed;

    error ClaimPaused();
    error ClaimAlreadyProcessed(uint256 rewardId);
    error InvalidSignature();
    error ClaimExpired();
    error InvalidChain();
    error ZeroAddress();
    /// @notice Escrow cannot cover payout plus fee for this claim.
    error InsufficientEscrow(uint256 required, uint256 available);
    /// @notice Withdrawal exceeds fees actually accrued.
    error TreasuryUnderfunded(uint256 requested, uint256 available);

    constructor(address token_, address signer_, address treasury_) Ownable(msg.sender) {
        if (token_ == address(0) || signer_ == address(0) || treasury_ == address(0)) {
            revert ZeroAddress();
        }
        rewardToken = IERC20(token_);
        signer = signer_;
        treasury = treasury_;
        // EIP-712 domain includes the chain id for cross-chain replay protection.
        uint256 chainId;
        assembly {
            chainId := chainid()
        }
        DOMAIN_SEPARATOR = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256("bagworkRH"),
                keccak256("1"),
                chainId,
                address(this)
            )
        );
    }

    /**
     * @notice Claim an approved reward with a valid signed authorization.
     * @param rewardId Unique platform reward identifier.
     * @param wallet Wallet that owns the reward (msg.sender must match).
     * @param amount Amount in the reward token's smallest units.
     * @param nonce Single-use claim nonce.
     * @param deadline Unix timestamp after which the authorization expires.
     * @param signature Off-chain signer's EIP-712 signature.
     *
     * @dev The creator receives EXACTLY `amount` — the signed value. The 15%
     * platform fee is withheld from escrow in addition to the payout, so the
     * brand must have funded `amount + fee` beforehand. A claim whose payout
     * plus fee is not fully covered reverts rather than paying the creator
     * less than signed, which would be a broken promise to a creator who has
     * already done the work.
     */
    function claim(
        uint256 rewardId,
        address wallet,
        uint256 amount,
        uint256 nonce,
        uint256 deadline,
        bytes calldata signature
    ) external nonReentrant {
        if (claimingPaused) revert ClaimPaused();
        if (msg.sender != wallet) revert InvalidSignature();
        if (block.timestamp > deadline) revert ClaimExpired();

        if (claimed[rewardId]) revert ClaimAlreadyProcessed(rewardId);

        bytes32 structHash = keccak256(
            abi.encode(CLAIM_TYPEHASH, wallet, rewardId, address(rewardToken), amount, nonce, deadline, block.chainid)
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR, structHash));
        address recovered = digest.recover(signature);
        if (recovered != signer) revert InvalidSignature();

        claimed[rewardId] = true;

        // The fee is computed on top of the signed payout and withheld here.
        // The creator is paid the full signed `amount` below; the fee simply
        // stays in the contract and is accounted to treasury.
        uint256 fee = (amount * PLATFORM_FEE_BPS) / BPS_DENOMINATOR;
        uint256 required = amount + fee;

        // Solvency check: reject the claim rather than underpay the creator or
        // let the fee eat into funds owed to other creators.
        uint256 spendable = totalDeposited - totalPaid - totalFeesAccrued + totalFeesWithdrawn;
        if (spendable < required) revert InsufficientEscrow(required, spendable);

        totalPaid += amount;
        totalFeesAccrued += fee;

        bool ok = rewardToken.transfer(wallet, amount);
        require(ok, "RewardDistributor: transfer failed");

        emit RewardClaimed(rewardId, wallet, address(rewardToken), amount, nonce);
        emit PlatformFeeAccrued(rewardId, wallet, amount, fee);
    }

    /// @notice Emergency pause for all claiming (owner only).
    function setClaimingPaused(bool paused_) external onlyOwner {
        claimingPaused = paused_;
        emit ClaimingPaused(paused_);
    }

    /// @notice Rotate the authorization signer (owner only).
    function setSigner(address newSigner_) external onlyOwner {
        if (newSigner_ == address(0)) revert ZeroAddress();
        emit SignerChanged(signer, newSigner_);
        signer = newSigner_;
    }

    /// @notice Deposit reward tokens into escrow (owner only).
    /// @dev Use `requiredDeposit(payout)` to work out the deposit needed to fund
    /// a payout including its platform fee.
    function deposit(uint256 amount) external onlyOwner {
        require(rewardToken.transferFrom(msg.sender, address(this), amount), "deposit transferFrom failed");
        totalDeposited += amount;
        emit Deposit(address(rewardToken), amount);
    }

    /**
     * @notice Platform fee for a given payout, in token smallest units.
     * @dev Exposed so the brand-facing quote and the contract cannot disagree.
     */
    function feeFor(uint256 payout) public pure returns (uint256) {
        return (payout * PLATFORM_FEE_BPS) / BPS_DENOMINATOR;
    }

    /**
     * @notice Total a brand must deposit to fund `payout` (payout + fee).
     * @dev The number a campaign budget should be divided by, not the payout.
     * A $2,500 budget funds $2,173.91 of payouts plus $326.09 of fees — 434
     * posts at $5, each creator paid the full $5.
     */
    function requiredDeposit(uint256 payout) external pure returns (uint256) {
        return payout + feeFor(payout);
    }

    /// @notice Escrow currently available to fund a further payout + fee.
    function spendableEscrow() public view returns (uint256) {
        return totalDeposited - totalPaid - totalFeesAccrued + totalFeesWithdrawn;
    }

    /// @notice Fees accrued but not yet withdrawn.
    function treasuryBalance() public view returns (uint256) {
        return totalFeesAccrued - totalFeesWithdrawn;
    }

    /**
     * @notice Withdraw accrued platform fees to the treasury address.
     * @dev Bounded by fees actually accrued. The previous `withdraw(uint256)`
     * could move any token held by the contract, including escrow still owed
     * to creators — an owner key compromise drained every pending payout. This
     * can only ever move money that is genuinely the platform's fee income.
     */
    function withdrawTreasury(uint256 amount) external onlyOwner {
        uint256 available = treasuryBalance();
        if (amount > available) revert TreasuryUnderfunded(amount, available);
        totalFeesWithdrawn += amount;
        require(rewardToken.transfer(treasury, amount), "treasury transfer failed");
        emit TreasuryWithdrawal(treasury, amount);
    }

    /// @notice Change the fee recipient (owner only). A multisig in production.
    function setTreasury(address newTreasury_) external onlyOwner {
        if (newTreasury_ == address(0)) revert ZeroAddress();
        emit TreasuryChanged(treasury, newTreasury_);
        treasury = newTreasury_;
    }
}