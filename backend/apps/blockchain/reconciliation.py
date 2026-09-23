"""Reconciliation between the internal ledger and the chain (Spec 04).

The on-chain token balance held by the RewardDistributor is *not* the same as
the internal ledger. Reconciliation reports the difference for ops review.
"""
import logging
from decimal import Decimal

from django.conf import settings

from .models import LedgerAction, LedgerEntry, TokenConfig
from .services import chain_enabled, get_web3

logger = logging.getLogger("apps.blockchain.reconciliation")

ERC20_BALANCE_OF_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    }
]


def internal_claimed_total(token: TokenConfig) -> Decimal:
    """Sum of confirmed claim amounts for a token from the internal ledger."""
    rows = LedgerEntry.objects.filter(
        action=LedgerAction.CLAIM_CONFIRMED, token_symbol=token.symbol
    )
    return sum((r.amount for r in rows), Decimal("0"))


def onchain_held_balance(token: TokenConfig) -> Decimal | None:
    """Token balance held by the distributor contract (None when disabled)."""
    w3 = get_web3()
    if w3 is None or not settings.CONTRACT_ADDRESS:
        return None
    try:  # pragma: no cover - depends on live RPC
        contract = w3.eth.contract(address=token.address, abi=ERC20_BALANCE_OF_ABI)
        raw = contract.functions.balanceOf(settings.CONTRACT_ADDRESS).call()
        return Decimal(raw) / (Decimal(10) ** token.decimals)
    except Exception as exc:  # pragma: no cover
        logger.warning("Reconciliation balance lookup failed: %s", exc)
        return None


def reconcile() -> list[dict]:
    """Compare each enabled token's ledger vs chain and report differences."""
    if not chain_enabled():
        return [
            {
                "status": "disabled",
                "reason": "RPC_URL/CONTRACT_ADDRESS not configured",
            }
        ]

    results = []
    for token in TokenConfig.objects.filter(enabled=True):
        internal = internal_claimed_total(token)
        onchain = onchain_held_balance(token)
        entry = {
            "symbol": token.symbol,
            "chain_id": token.chain_id,
            "internal_claimed": str(internal),
            "onchain_held": str(onchain) if onchain is not None else "unavailable",
        }
        if onchain is not None:
            entry["difference"] = str(onchain - internal)
        results.append(entry)
    return results