"""Internal accounting ledger (Spec 04).

Records every financial movement in the platform's own books:
  reward earned -> approved -> claim created -> claimed on-chain (tx hash).

The on-chain token balance is a *separate* source of truth; reconciliation
compares this ledger with the distributor contract balance.
"""
from decimal import Decimal

from .models import LedgerAction, LedgerEntry


def record(  # noqa: PLR0913 - a ledger entry is an explicit, wide record
    action: LedgerAction,
    *,
    seller=None,
    reward=None,
    claim=None,
    wallet=None,
    token_symbol: str = "",
    amount: Decimal = Decimal("0"),
    amount_smallest_unit: int = 0,
    transaction_hash: str = "",
) -> LedgerEntry:
    symbol = token_symbol or (claim.token_symbol if claim else "") or (
        reward.token_symbol if reward else ""
    )
    return LedgerEntry.objects.create(
        action=action,
        seller=seller,
        reward=reward,
        claim=claim,
        wallet=wallet,
        token_symbol=symbol,
        amount=amount,
        amount_smallest_unit=amount_smallest_unit or (
            claim.amount_smallest_unit if claim else 0
        ),
        transaction_hash=transaction_hash,
    )