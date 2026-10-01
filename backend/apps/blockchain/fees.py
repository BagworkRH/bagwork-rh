"""Platform fee arithmetic (Spec 04).

The 15% platform fee is charged to the BRAND on top of the creator payout and
is never deducted from the payout itself. A creator promised $5 for verified
work receives $5; the brand pays $5.75. An under-funded campaign pays fewer
claims rather than smaller ones.

All functions mirror `RewardDistributor.feeFor` / `requiredDeposit` exactly.
`test_platform_fee.py` cross-checks this arithmetic against the compiled
contract so a change to one side without the other fails CI.

Rounding is floor-based to match Solidity integer division, so the backend can
never quote a brand one unit more than the contract would accept.
"""
from decimal import ROUND_DOWN, Decimal

from django.conf import settings

BPS_DENOMINATOR = 10_000
ONE = Decimal(1)


def _to_units(value: Decimal) -> int:
    """Decimal -> integer smallest units, at the default 18 decimals."""
    scaled = value.scaleb(default_token_decimals())
    return int(scaled.to_integral_value(rounding=ROUND_DOWN))


def default_token_decimals() -> int:
    from apps.blockchain.services import (  # noqa: PLC0415 - avoids an import cycle
        default_token_decimals as _decimals,
    )

    return _decimals()


def fee_bps() -> int:
    """Platform fee in basis points (1500 = 15%)."""
    return int(getattr(settings, "PLATFORM_FEE_BPS", 1500))


def fee_rate() -> Decimal:
    """Fee as a decimal rate (0.15 for 15%)."""
    return Decimal(fee_bps()) / BPS_DENOMINATOR


def platform_fee(payout) -> Decimal:
    """Fee charged on top of `payout`, in payout units.

    Floored to mirror the contract's integer division (see RewardDistributor.
    feeFor), so a brand is never quoted a unit more than the chain would
    accept. Sub-unit fees floor to zero rather than rounding up.
    """
    payout = Decimal(payout)
    if payout <= 0:
        return Decimal(0)
    units = _to_units(payout)
    fee_units = units * fee_bps() // BPS_DENOMINATOR
    return Decimal(fee_units).scaleb(-default_token_decimals())


def total_cost(payout) -> Decimal:
    """What the brand pays to fund a payout: payout + fee."""
    return Decimal(payout) + platform_fee(payout)


def payouts_from_budget(budget, payout) -> int:
    """How many claims of `payout` a `budget` funds, fees included.

    This is the "fewer posts, not smaller posts" rule: a $2,500 budget at a $5
    payout funds 434 claims (434 x $5.75 = $2,495.50), each creator paid $5.
    """
    cost = total_cost(payout)
    if cost <= 0:
        return 0
    return int((Decimal(budget) / cost).to_integral_value(rounding=ROUND_DOWN))


def brand_cost_for(payouts, payout) -> Decimal:
    """Total a brand pays to fund `payouts` claims at `payout` each."""
    return total_cost(payout) * Decimal(payouts)
