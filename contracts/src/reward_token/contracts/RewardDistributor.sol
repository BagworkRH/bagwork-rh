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
 * The contract is intentionally minimal: authorized distributor, claim
 * allocation, claimed status, emergency pause, ownership.
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

    constructor(address token_, address signer_) Ownable(msg.sender) {
        if (token_ == address(0) || signer_ == address(0)) revert ZeroAddress();
        rewardToken = IERC20(token_);
        signer = signer_;
        // EIP-712 domain includes the chain id for cross-chain replay protection.
        uint256 chainId;
        assembly {
            chainId := chainid()
        }
        DOMAIN_SEPARATOR = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256("CryptoRewards"),
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

        bool ok = rewardToken.transfer(wallet, amount);
        require(ok, "RewardDistributor: transfer failed");

        emit RewardClaimed(rewardId, wallet, address(rewardToken), amount, nonce);
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
    function deposit(uint256 amount) external onlyOwner {
        require(rewardToken.transferFrom(msg.sender, address(this), amount), "deposit transferFrom failed");
        emit Deposit(address(rewardToken), amount);
    }

    /// @notice Withdraw remaining tokens (owner only; used after campaign closes).
    function withdraw(uint256 amount) external onlyOwner {
        require(rewardToken.transfer(msg.sender, amount), "withdraw transfer failed");
    }
}