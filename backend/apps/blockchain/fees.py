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

# Fallback only. Real callers pass the token's own decimals; this exists so a
# bare arithmetic call still works, but relying on it for a real token is a
# bug: USDC is 6 decimals, not 18, and quoting a fee at the wrong precision
# makes the backend disagree with the contract.
DEFAULT_DECIMALS = 18


def fee_bps() -> int:
    """Platform fee in basis points (1500 = 15%)."""
    return int(getattr(settings, "PLATFORM_FEE_BPS", 1500))


def fee_rate() -> Decimal:
    """Fee as a decimal rate (0.15 for 15%)."""
    return Decimal(fee_bps()) / BPS_DENOMINATOR


def to_units(value, decimals: int | None = None) -> int:
    """Decimal -> integer smallest units at `decimals` precision."""
    places = DEFAULT_DECIMALS if decimals is None else decimals
    scaled = Decimal(value).scaleb(places)
    return int(scaled.to_integral_value(rounding=ROUND_DOWN))


def from_units(units: int, decimals: int | None = None) -> Decimal:
    """Integer smallest units -> Decimal at `decimals` precision."""
    places = DEFAULT_DECIMALS if decimals is None else decimals
    return Decimal(units).scaleb(-places)


def platform_fee(payout, decimals: int | None = None) -> Decimal:
    """Fee charged on top of `payout`, in payout units.

    `decimals` must be the payout token's precision — pass the campaign's
    token decimals, never a default. The fee is computed in integer smallest
    units so it matches `RewardDistributor.feeFor` exactly, including its
    flooring division: a brand is never quoted a unit more than the contract
    would charge, and a sub-unit fee floors to zero rather than rounding up
    into a charge the chain would not make.
    """
    payout = Decimal(payout)
    if payout <= 0:
        return Decimal(0)
    places = DEFAULT_DECIMALS if decimals is None else decimals
    fee_units = to_units(payout, places) * fee_bps() // BPS_DENOMINATOR
    return from_units(fee_units, places)


def total_cost(payout, decimals: int | None = None) -> Decimal:
    """What a brand pays to fund a payout: payout + fee."""
    return Decimal(payout) + platform_fee(payout, decimals)



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
