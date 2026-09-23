"""ABI encoding for on-chain claim transactions (Spec 04).

The platform encodes the `RewardDistributor.claim(...)` calldata server-side,
so wallet clients never hand-roll ABI encoding: the frontend asks the wallet
provider to send a transaction to `to` with `data` (see the claim
authorization endpoint).

The selector and argument layout must match
`contracts/src/reward_token/contracts/RewardDistributor.sol`:

    function claim(
        uint256 rewardId,
        address wallet,
        uint256 amount,
        uint256 nonce,
        uint256 deadline,
        bytes calldata signature
    ) external
"""
from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_hash.auto import keccak
from eth_utils import to_checksum_address
from hexbytes import HexBytes

CLAIM_FUNCTION_SIGNATURE = "claim(uint256,address,uint256,uint256,uint256,bytes)"

# First 4 bytes of keccak256 of the canonical function signature.
CLAIM_SELECTOR = HexBytes(keccak(CLAIM_FUNCTION_SIGNATURE.encode()))[:4]

CLAIM_ARG_TYPES = ["uint256", "address", "uint256", "uint256", "uint256", "bytes"]


def encode_claim_calldata(  # noqa: PLR0913 - mirrors the contract's claim() arguments
    *,
    reward_id: int,
    wallet: str,
    amount: int,
    nonce: int,
    deadline: int,
    signature: str,
) -> str:
    """Encode a `claim(...)` call as 0x-prefixed calldata.

    `amount` is in the token's smallest units and `deadline` is epoch seconds,
    exactly as covered by the EIP-712 authorization signature.
    """
    encoded_args = abi_encode(
        CLAIM_ARG_TYPES,
        [
            int(reward_id),
            HexBytes(wallet),
            int(amount),
            int(nonce),
            int(deadline),
            HexBytes(signature),
        ],
    )
    return "0x" + HexBytes(CLAIM_SELECTOR + encoded_args).hex()


def decode_claim_calldata(calldata: str) -> dict:
    """Decode calldata produced by `encode_claim_calldata` (round-trip tests)."""
    raw = HexBytes(calldata)
    if raw[:4] != CLAIM_SELECTOR:
        raise ValueError("Calldata is not a claim(...) call.")
    reward_id, wallet, amount, nonce, deadline, signature = abi_decode(
        CLAIM_ARG_TYPES, bytes(raw[4:])
    )
    return {
        "reward_id": int(reward_id),
        "wallet": to_checksum_address(wallet),
        "amount": int(amount),
        "nonce": int(nonce),
        "deadline": int(deadline),
        "signature": HexBytes(signature).hex(),
    }