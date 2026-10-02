"""On-chain verification of a brand funding transfer.

Confirming a deposit is the one operation where being wrong creates money that
does not exist. Everything else on this platform is a policy decision; this is
a question with a right answer that only the chain can give: *did this money
actually arrive, to us, in the right token, in the right amount?* A brand
answering that question about its own money is a brand writing its own bank
statement, so the answer is read from a receipt instead.

Every check fails closed. An unreachable node, a missing token in the
allowlist, a receipt that cannot be fetched, a reorg, a short confirmation
window — all of them leave the deposit PENDING. There is deliberately no
"assume it landed" path, because the cost of guessing wrong is a platform
promising creators money it will never have.

The recipient must be the platform treasury. Without that check a brand could
point at a real, successful, correctly-valued transfer of its own stablecoin to
an address it controls and have the platform call it funding.
"""
import logging
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from web3 import Web3

from apps.rewards.exceptions import RewardEngineError

from .models import TokenConfig
from .services import get_web3

logger = logging.getLogger("apps.blockchain.deposits")

# ERC-20 Transfer(address,address,uint256) — the single event that proves a
# stablecoin balance actually moved.
#
# `removeprefix` rather than a blind `[2:]`: hexbytes has shipped versions where
# `.hex()` includes a "0x" and versions where it does not, so slicing two
# characters off an unnormalised value silently corrupts the constant. Getting
# it wrong makes every genuine transfer fail to match, which is indistinguishable
# from a chain that never received the money — so the value is normalised once
# here and compared bare everywhere else.
TRANSFER_TOPIC = Web3.keccak(text="Transfer(address,address,uint256)").hex().lower().removeprefix("0x")

# Transfer indexes all three of its fields, so a genuine one always has exactly
# three topics. Fewer is a different event, or a malformed log.
TRANSFER_TOPIC_COUNT = 3


def _as_int(value) -> int:
    """Read a log's `data` as an integer, however the node encoded it.

    Receipts return `data` as HexBytes. `int(HexBytes, 16)` does not work —
    `int()` treats a bytes object as a literal string — and raises
    `ValueError`, so the amount read has to go through the big-endian bytes.
    A hex string is still accepted so a receipt from an unexpected client does
    not turn into a crash.
    """
    if isinstance(value, (bytes, bytearray)):
        return int.from_bytes(bytes(value), "big")
    return int(str(value), 16)


@dataclass(frozen=True)
class VerifiedTransfer:
    """What the chain says happened, for the audit log and for dispute.

    Recorded rather than discarded so a rejected deposit can be explained later
    without re-querying a node that may since have pruned the receipt.
    """

    tx_hash: str
    chain_id: int
    block_number: int
    confirmations: int
    token_symbol: str
    token_address: str
    from_address: str
    to_address: str
    amount: Decimal

    def as_metadata(self) -> dict:
        return {
            "tx_hash": self.tx_hash,
            "chain_id": self.chain_id,
            "block_number": self.block_number,
            "confirmations": self.confirmations,
            "token_symbol": self.token_symbol,
            "token_address": self.token_address,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "amount": str(self.amount),
        }


def required_confirmations() -> int:
    """How deep a deposit must be buried before it counts as final.

    A transaction with zero confirmations can still be replaced or reorged out
    of the chain, so crediting it immediately is crediting a promise.
    """
    return max(0, int(getattr(settings, "FUNDING_CONFIRMATIONS", 3)))


def treasury_address() -> str:
    """The address funding must actually reach.

    This is the platform's own address, never one supplied by the caller. A
    verification that accepts a caller-chosen recipient is not a check.
    """
    address = str(getattr(settings, "FUNDING_TREASURY_ADDRESS", "") or "").strip()
    if not address:
        raise RewardEngineError(
            "FUNDING_TREASURY_ADDRESS is not configured, so no deposit can be verified. "
            "Refusing to confirm funding to an unknown address."
        )
    return Web3.to_checksum_address(address)


def _require_reachable():
    """A connected node, or an explicit failure. Never a guess."""
    w3 = get_web3()
    if w3 is None:
        raise RewardEngineError(
            "Cannot reach the chain to verify this deposit. The deposit stays pending "
            "and will be confirmed automatically once the RPC is reachable. This is "
            "deliberate: a deposit is never credited because the platform could not "
            "check it."
        )
    return w3


def _require_allowlisted_token(chain_id: int, symbol: str) -> TokenConfig:
    """The token must be a known, enabled contract on this chain.

    Reading decimals from the allowlist rather than assuming them is what keeps
    the amount check exact; guessing 6 when the token has 18 would let a
    rounding-error-sized transfer satisfy a large deposit.
    """
    token = TokenConfig.objects.filter(chain_id=chain_id, symbol__iexact=symbol).first()
    if token is None:
        raise RewardEngineError(
            f"{symbol} is not on the allowlist for chain {chain_id}, so a deposit in it "
            "cannot be verified. Refusing to credit a token the platform has never checked."
        )
    if not token.enabled:
        raise RewardEngineError(f"{symbol} is disabled for chain {chain_id}.")
    return token


def _require_expected_chain(w3, chain_id: int) -> None:
    """The node must be on the chain the deposit claims.

    A hash is not chain-qualified. The same string could exist on testnet and
    mainnet with different meanings, so the node's own id is checked rather
    than the URL's hostname.
    """
    try:
        actual = w3.eth.chain_id
    except Exception as exc:
        raise RewardEngineError(
            "The chain did not report its id; the deposit was not verified."
        ) from exc
    if int(actual) != int(chain_id):
        raise RewardEngineError(
            f"This deposit claims chain {chain_id} but the node is on chain {actual}. "
            "Refusing to confirm against the wrong network."
        )


def _require_successful_receipt(w3, tx_hash: str, chain_id: int):
    """A receipt that exists and did not revert.

    A reverted transfer emits a receipt with status 0. Treating it as a
    deposit would be crediting a transaction that moved no money at all.
    """
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
    except Exception as exc:
        raise RewardEngineError(
            "The transaction was not found on chain, so the deposit was not verified. "
            "Check the hash, and that it was sent on the expected network."
        ) from exc
    if receipt is None:
        raise RewardEngineError(
            "No receipt found for that transaction. It may not be mined yet, or the "
            "hash may be wrong. The deposit stays pending until it can be seen on chain."
        )
    status = getattr(receipt, "status", 1)
    if int(status) != 1:
        raise RewardEngineError("That transaction failed on chain, so no funds arrived.")
    return receipt


def _require_enough_confirmations(w3, receipt, needed: int) -> int:
    """Buried deep enough that the chain will not take it back.

    Confirmations are counted against the current head rather than a fixed
    block, and the head is read once so the arithmetic cannot straddle a new
    block and produce an off-by-one.
    """
    try:
        head = w3.eth.block_number
    except Exception as exc:
        raise RewardEngineError(
            "Could not read the chain head to count confirmations; the deposit was not verified."
        ) from exc
    confirmations = int(head) - int(receipt.blockNumber)
    if confirmations < needed:
        raise RewardEngineError(
            f"That transfer has {confirmations} confirmation(s); {needed} are required "
            "before funding is credited. It will be confirmed automatically once buried."
        )
    return confirmations


def _find_transfer_to_treasury(receipt, token: TokenConfig, treasury: str):
    """The ERC-20 transfer that paid us, in the right token.

    Scans only logs emitted by the allowlisted token's own address. Matching on
    the topic alone would accept any contract emitting a Transfer-shaped event
    — a wrapper, a scam token, or an unrelated transfer.
    """
    treasury_lower = treasury.lower()
    for log in receipt.get("logs", []):
        if int(log["address"], 16) != int(token.address, 16):
            continue
        topics = log.get("topics") or []
        # A real Transfer has three indexed fields; anything shorter is not it.
        if len(topics) < TRANSFER_TOPIC_COUNT:
            continue
        # Both sides are normalised bare hex, so a node that prefixes "0x" and
        # one that does not are both matched.
        if topics[0].hex().lower().removeprefix("0x") != TRANSFER_TOPIC:
            continue
        recipient = "0x" + topics[2].hex()[-40:]
        if recipient.lower() != treasury_lower:
            continue
        raw_amount = _as_int(log["data"])
        sender = "0x" + topics[1].hex()[-40:]
        return sender, Web3.to_checksum_address(recipient), raw_amount
    return None

def verify_deposit(*, chain_id, tx_hash, token_symbol, expected_amount) -> VerifiedTransfer:
    """Prove a deposit really arrived, or raise explaining why it did not.

    Returns a `VerifiedTransfer` describing the receipt, or raises
    `RewardEngineError` with a message a brand can act on. Raising is the safe
    outcome in every ambiguous case: an unverified deposit is a delay, whereas
    a wrongly verified one is a shortfall the platform pays out of its own
    balance to real creators.
    """
    w3 = _require_reachable()
    _require_expected_chain(w3, int(chain_id))
    token = _require_allowlisted_token(int(chain_id), token_symbol)
    treasury = treasury_address()
    receipt = _require_successful_receipt(w3, tx_hash, int(chain_id))
    confirmations = _require_enough_confirmations(w3, receipt, required_confirmations())

    found = _find_transfer_to_treasury(receipt, token, treasury)
    if found is None:
        raise RewardEngineError(
            f"That transaction does not contain a {token.symbol} transfer to the platform "
            "treasury. Nothing was credited."
        )
    sender, recipient, raw_amount = found

    amount = Decimal(raw_amount) / (Decimal(10) ** token.decimals)
    expected_amount = Decimal(str(expected_amount))

    if amount < expected_amount:
        raise RewardEngineError(
            f"That transfer sent {amount} {token.symbol}, but the deposit claims "
            f"{expected_amount}. Nothing was credited — a deposit is credited for what "
            "actually arrived, not for what was claimed."
        )

    return VerifiedTransfer(
        tx_hash=tx_hash,
        chain_id=int(chain_id),
        block_number=int(receipt.blockNumber),
        confirmations=confirmations,
        token_symbol=token.symbol,
        token_address=Web3.to_checksum_address(token.address),
        from_address=Web3.to_checksum_address(sender),
        to_address=recipient,
        amount=amount,
    )


    status = getattr(receipt, "status", 1)
    if int(status) != 1:
        raise RewardEngineError("That transaction failed on chain, so no funds arrived.")
    return receipt
