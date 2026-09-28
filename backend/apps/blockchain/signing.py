"""EIP-712 claim-authorization signing (Spec 04).

The RewardDistributor contract validates a typed-data signature with domain
separation over { chainId, verifyingContract, name, version }. This module
mirrors the contract's struct hash + digest construction and signs with the
platform claim signer (private key from CLAIM_SIGNER env).

Signing scheme (matches `contracts/.../RewardDistributor.sol`):
  structHash = keccak(abi.encode(TYPEHASH, wallet, rewardId, token,
                                 amount, nonce, deadline, chainId))
  domainSep  = keccak(abi.encode(DOMAIN_TYPEHASH, nameHash, versionHash,
                                 chainId, contractAddress))
  digest     = keccak(b"\\x19\\x01" + domainSep + structHash)
  signature  = ECDSA.sign(digest, signerKey)   # 65 bytes r|s|v as ethers does
"""
import calendar
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from eth_abi import encode as abi_encode
from eth_account import Account
from eth_hash.auto import keccak
from eth_keys import keys
from eth_utils import to_canonical_address, to_checksum_address
from hexbytes import HexBytes

# The exact claim type used in the contract.
CLAIM_TYPEHASH = HexBytes(
    keccak(
        b"Claim(address wallet,uint256 rewardId,address token,uint256 amount,"
        b"uint256 nonce,uint256 deadline,uint256 chainId)"
    )
)
DOMAIN_TYPEHASH = HexBytes(
    keccak(
        b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
    )
)
DOMAIN_NAME = b"bagworkRH"
DOMAIN_VERSION = b"1"

# ECDSA signature layout used by ethers / OpenZeppelin: r|s|v, 65 bytes, with
# v in {27, 28}; `eth_keys` expects v in {0, 1}.
SIGNATURE_LENGTH = 65
SIGNATURE_V_OFFSET = 27


def _padded_address(address):
    """Address right-padded to 32 bytes for indexing topics."""
    return HexBytes(to_canonical_address(address)).rjust(32, b"\x00")


def build_domain_separator(chain_id, contract_address, name=None, version=None):
    name = (name or DOMAIN_NAME)
    version = (version or DOMAIN_VERSION)
    if isinstance(name, str):
        name = name.encode()
    if isinstance(version, str):
        version = version.encode()
    data = abi_encode(
        ["bytes32", "bytes32", "bytes32", "uint256", "address"],
        [
            DOMAIN_TYPEHASH,
            HexBytes(keccak(name)),
            HexBytes(keccak(version)),
            chain_id,
            to_canonical_address(contract_address),
        ],
    )
    return HexBytes(keccak(data))


def build_claim_struct_hash(  # noqa: PLR0913,PLR0917 - mirrors the contract's Claim struct
    wallet, reward_id, token_address, amount, nonce, deadline, chain_id
):
    """`amount`, `nonce`, `deadline` are integers (smallest units / epoch seconds)."""
    data = abi_encode(
        ["bytes32", "address", "uint256", "address", "uint256", "uint256", "uint256", "uint256"],
        [
            CLAIM_TYPEHASH,
            to_canonical_address(wallet),
            reward_id,
            to_canonical_address(token_address),
            amount,
            nonce,
            deadline,
            chain_id,
        ],
    )
    return HexBytes(keccak(data))


def build_claim_digest(  # noqa: PLR0913,PLR0917 - mirrors the contract's Claim struct
    wallet, reward_id, token_address, amount, nonce, deadline, chain_id, contract_address
):
    struct_hash = build_claim_struct_hash(
        wallet, reward_id, token_address, amount, nonce, deadline, chain_id
    )
    domain_sep = build_domain_separator(chain_id, contract_address)
    return HexBytes(keccak(b"\x19\x01" + domain_sep + struct_hash))


def serialize_signature(signature: bytes) -> str:
    """65-byte r|s|v -> 0x-prefixed hex (ethers / OpenZeppelin ECDSA format)."""
    return "0x" + signature.hex()


def sign_claim_digest(digest, private_key: str) -> str:
    """Sign the 32-byte EIP-712 digest with the claim signer (65-byte vrs).

    `unsafe_sign_hash` signs the digest *as-is* (no EIP-191 prefix), which is
    exactly what `ethers.Wallet.signTypedData` does and what the contract's
    OpenZeppelin `ECDSA.recover(digest, signature)` expects. The "unsafe" name
    refers to the caller being responsible for the message format — here the
    digest is fully domain-separated, so that responsibility is met.
    """
    signed = Account.unsafe_sign_hash(HexBytes(digest), private_key=(private_key or ""))
    return serialize_signature(bytes(signed.signature))


def recover_claim_signer(digest, signature: str) -> str:
    """Recover the address that produced `signature` for a digest.

    Uses `eth_keys`, the same primitive the contract's OpenZeppelin
    `ECDSA.recover(digest, signature)` performs: recover the public key from
    the 32-byte digest, then derive the address.

    `eth_keys` wants `v` in {0, 1} whereas ethers/OpenZeppelin emit {27, 28},
    so the recovery byte is normalized here (the on-chain library accepts both).
    """
    raw = bytes(HexBytes(signature))
    if len(raw) != SIGNATURE_LENGTH:
        raise ValueError(
            f"Expected a {SIGNATURE_LENGTH}-byte signature, got {len(raw)} bytes."
        )
    if raw[64] >= SIGNATURE_V_OFFSET:
        raw = raw[:64] + bytes([raw[64] - SIGNATURE_V_OFFSET])

    sig = keys.Signature(raw)
    public_key = sig.recover_public_key_from_msg_hash(HexBytes(digest))
    return to_checksum_address(public_key.to_address())


def signer_address(private_key: str) -> str:
    return to_checksum_address(Account.from_key(private_key).address)


def verify_claim_signature(digest, signature: str, expected_address: str) -> bool:
    try:
        recovered = recover_claim_signer(digest, signature)
    except Exception:
        return False
    return to_checksum_address(recovered) == to_checksum_address(expected_address)


def reward_amount_smallest(amount: Decimal, decimals: int) -> int:
    """Convert an off-chain Decimal reward to integer smallest token units."""
    return int(amount * (Decimal(10) ** decimals))


def claim_deadline(expired_at) -> int:
    """Claim expiry as epoch seconds (UTC) for the authorization message.

    `calendar.timegm` is used (not `time.mktime`) because the tuple is UTC;
    `mktime` would interpret it in the server's local timezone and shift the
    deadline that the contract validates.
    """
    value = expired_at or (timezone.now() + timedelta(hours=24))
    if value.tzinfo is None:
        value = timezone.make_aware(value, timezone.utc)
    return calendar.timegm(value.utctimetuple())