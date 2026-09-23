"""Blockchain event listener (Spec 04).

Listens for RewardClaimed events emitted by the RewardDistributor contract,
marks the matching claim CONFIRMED and the reward CLAIMED, and records the
ledger entry.

When no RPC is configured the listener returns a "disabled" status so the
Celery scheduler can run it safely during development.
"""
import logging

from django.conf import settings
from eth_abi import decode as abi_decode
from eth_hash.auto import keccak
from eth_utils import to_checksum_address
from hexbytes import HexBytes

from apps.wallets.models import Claim, ClaimStatus
from apps.wallets.services import mark_claim_confirmed

from .services import get_web3

logger = logging.getLogger("apps.blockchain.listener")

# RewardClaimed(uint256 rewardId, address wallet, address token, uint256 amount, uint256 nonce)
CLAIM_EVENT_SIGNATURE = "RewardClaimed(uint256,address,address,uint256,uint256)"
CLAIM_TOPIC0 = HexBytes(keccak(CLAIM_EVENT_SIGNATURE.encode()))

REWARD_DISTRIBUTOR_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "rewardId", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "wallet", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "token", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "nonce", "type": "uint256"},
        ],
        "name": "RewardClaimed",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "Deposit",
        "type": "event",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "rewardId", "type": "uint256"},
            {"internalType": "address", "name": "wallet", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "uint256", "name": "nonce", "type": "uint256"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
            {"internalType": "bytes", "name": "signature", "type": "bytes"},
        ],
        "name": "claim",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bool", "name": "paused_", "type": "bool"}],
        "name": "setClaimingPaused",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "newSigner_", "type": "address"}],
        "name": "setSigner",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


def decode_reward_claimed_log(topics, data):
    """Decode event log topics/data into a RewardClaimed payload dict.

    topics: list of 32-byte HexBytes-like; data: bytes.
    Indexed params (rewardId, wallet, token) are in topics; the rest in data.
    """
    if not topics or HexBytes(topics[0]).hex() != CLAIM_TOPIC0.hex():
        return None

    reward_id = int(HexBytes(topics[1]).hex(), 16)
    wallet = to_checksum_address(HexBytes(topics[2])[12:])
    token = to_checksum_address(HexBytes(topics[3])[12:])

    amount, nonce = abi_decode(["uint256", "uint256"], data)
    return {
        "reward_id": reward_id,
        "wallet": wallet,
        "token": token,
        "amount": int(amount),
        "nonce": int(nonce),
    }


def _find_claim_for_event(event):
    """Locate the claim matching a RewardClaimed event (nonce compared as int).

    Claim nonces are stored as 32-byte hex strings, while the event carries the
    nonce as a uint256. Comparing the raw values would fail whenever the hex
    string has leading zeros, so both sides are compared as integers.
    """
    expected_nonce = int(event["nonce"])
    candidates = (
        Claim.objects.select_related("reward", "wallet")
        .filter(reward_id=event["reward_id"])
        .exclude(nonce="")
    )
    for claim in candidates:
        try:
            if int(claim.nonce, 16) == expected_nonce:
                return claim
        except (TypeError, ValueError):
            continue
    return None


def handle_reward_claimed(event: dict, *, transaction_hash: str = "", actor=None) -> dict:
    """Mark the matching claim CONFIRMED / reward CLAIMED from an event.

    Idempotent: a claim that is already CONFIRMED returns `already-confirmed`,
    so re-scanning a block range is safe.
    """
    claim = _find_claim_for_event(event)
    if claim is None:
        return {
            "status": "no-matching-claim",
            "reward_id": event["reward_id"],
            "nonce": event["nonce"],
        }

    if claim.status == ClaimStatus.CONFIRMED:
        return {"status": "already-confirmed", "claim_id": claim.pk}

    mark_claim_confirmed(claim, transaction_hash, actor=actor)
    logger.info("Claim %s confirmed by on-chain event %s", claim.pk, transaction_hash)
    return {"status": "confirmed", "claim_id": claim.pk, "transaction_hash": transaction_hash}


def _distributor_contract(w3):
    return w3.eth.contract(address=settings.CONTRACT_ADDRESS, abi=REWARD_DISTRIBUTOR_ABI)


def poll_reward_claimed_events(from_block=None, to_block=None, *, lookback: int = 200) -> dict:
    """Poll the chain for RewardClaimed events (idempotent by claim nonce).

    Uses the contract's event filter (`get_logs`) rather than walking blocks,
    so a single RPC round-trip covers the range. Re-scanning is safe because
    `handle_reward_claimed` is idempotent.
    """
    w3 = get_web3()
    if w3 is None:
        return {"status": "disabled", "reason": "RPC_URL not configured"}
    if not settings.CONTRACT_ADDRESS:
        return {"status": "disabled", "reason": "CONTRACT_ADDRESS not configured"}

    latest = w3.eth.block_number
    start = max(int(from_block if from_block is not None else latest - lookback), 0)
    end = int(to_block if to_block is not None else latest)

    contract = _distributor_contract(w3)
    found = []
    for entry in contract.events.RewardClaimed().get_logs(from_block=start, to_block=end):
        args = entry["args"]
        event = {
            "reward_id": int(args["rewardId"]),
            "wallet": to_checksum_address(args["wallet"]),
            "token": to_checksum_address(args["token"]),
            "amount": int(args["amount"]),
            "nonce": int(args["nonce"]),
        }
        tx_hash = HexBytes(entry["transactionHash"]).hex()
        result = handle_reward_claimed(event, transaction_hash=tx_hash, actor=None)
        found.append({**event, "tx_hash": tx_hash, "result": result})

    return {
        "status": "ok" if found else "no-events",
        "events": found,
        "from": start,
        "to": end,
    }
