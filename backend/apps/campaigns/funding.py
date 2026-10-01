"""Brand funding: stablecoin deposits, the platform fee, and funded balance.

A brand funds its campaigns by sending stablecoin, and the platform pays
creators in the same stablecoin from it — there is no fiat conversion anywhere,
so the platform is not acting as an exchanger.

The token is USDG (Paxos Global Dollar), the stablecoin Robinhood Chain
documents. Being dollar-denominated is the point: a creator's payout holds its
value and does not expose them to a token's price, which is why creators are
not paid in the platform token. The symbol comes from
`settings.FUNDING_TOKEN_SYMBOL` so there is one definition rather than a
literal repeated across files.

The 15% platform fee is charged here, on the brand's deposit, and is NOT taken
from a creator's payout. The arithmetic is imported from
`apps.blockchain.fees` so a quote produced here is identical to what the
distributor contract accepts on chain; a second implementation would drift and
misquote real money.
"""
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.blockchain import fees
from apps.rewards.exceptions import RewardEngineError

from .models import BrandFunding, BrandProfile, BrandStatus, FundingStatus

TX_HASH_LENGTH = 66


def funding_token_symbol() -> str:
    """The stablecoin brands fund with and creators are paid in."""
    return str(getattr(settings, "FUNDING_TOKEN_SYMBOL", "USDG"))


class DuplicateFundingError(RewardEngineError):
    """This on-chain transfer was already recorded."""


def get_or_create_brand(user, *, company_name, contact_email="", actor=None) -> BrandProfile:
    """Create the brand profile for a user, or return the existing one."""
    existing = BrandProfile.objects.filter(user=user).first()
    if existing is not None:
        return existing
    brand = BrandProfile.objects.create(
        user=user,
        company_name=company_name.strip(),
        contact_email=(contact_email or user.email).strip(),
    )
    AuditLog.objects.create(
        actor=actor or user,
        action="BRAND_CREATED",
        object_type="BrandProfile",
        object_id=str(brand.pk),
        metadata={"company_name": brand.company_name},
    )
    return brand


def _validated_tx_hash(tx_hash: str) -> str:
    tx_hash = (tx_hash or "").strip()
    if not tx_hash.startswith("0x"):
        raise RewardEngineError("A transaction hash must be 0x-prefixed.")
    if len(tx_hash) != TX_HASH_LENGTH:
        raise RewardEngineError(
            f"A transaction hash must be {TX_HASH_LENGTH} characters (0x plus 64 hex digits)."
        )
    return tx_hash.lower()



def record_funding(  # noqa: PLR0913 - an explicit funding record
    brand,
    *,
    amount,
    chain_id,
    tx_hash,
    token_symbol=None,
    campaign=None,
    actor=None,
) -> BrandFunding:
    """Record a stablecoin deposit as funding.

    The deposit is stored as PENDING. A separate confirmation step — which
    requires an on-chain check — marks it CONFIRMED, and only confirmed
    deposits count toward a balance. Crediting money because a client said it
    arrived is just the client asserting that.
    """
    if brand.status == BrandStatus.SUSPENDED:
        raise RewardEngineError("This brand account is suspended and cannot be funded.")

    amount = Decimal(str(amount))
    if amount <= 0:
        raise RewardEngineError("A funding amount must be greater than zero.")

    tx_hash = _validated_tx_hash(tx_hash)

    try:
        with transaction.atomic():
            funding = BrandFunding.objects.create(
                brand=brand,
                amount=amount,
                chain_id=int(chain_id),
                token_symbol=token_symbol or funding_token_symbol(),
                tx_hash=tx_hash,
                campaign=campaign,
                status=FundingStatus.PENDING,
            )
    except IntegrityError as exc:
        # The unique constraint is the real guard against double-crediting;
        # this only turns it into a message the brand can act on. Matched on
        # the column pair rather than the constraint name: SQLite reports
        # "UNIQUE constraint failed: table.chain_id, table.tx_hash" and does
        # not name the constraint, so a name match silently misses on SQLite
        # and turns a replay into a 500.
        message = str(exc).lower()
        if "unique" in message and "tx_hash" in message:
            raise DuplicateFundingError(
                "This transaction has already been recorded as funding."
            ) from exc
        raise

    AuditLog.objects.create(
        actor=actor or brand.user,
        action="BRAND_FUNDING_RECORDED",
        object_type="BrandFunding",
        object_id=str(funding.pk),
        metadata={
            "amount": str(amount),
            "chain_id": int(chain_id),
            "tx_hash": tx_hash,
            "campaign": campaign.slug if campaign else None,
        },
    )
    return funding


def confirm_funding(funding, *, actor=None) -> BrandFunding:
    """Mark a deposit CONFIRMED once the on-chain transfer is verified."""
    if funding.status == FundingStatus.CONFIRMED:
        return funding
    if funding.status == FundingStatus.REJECTED:
        raise RewardEngineError("A rejected deposit cannot be confirmed.")

    funding.status = FundingStatus.CONFIRMED
    funding.confirmed_at = timezone.now()
    funding.save(update_fields=["status", "confirmed_at"])

    AuditLog.objects.create(
        actor=actor,
        action="BRAND_FUNDING_CONFIRMED",
        object_type="BrandFunding",
        object_id=str(funding.pk),
        metadata={"amount": str(funding.amount), "tx_hash": funding.tx_hash},
    )
    return funding


def _confirmed_total(queryset) -> Decimal:
    return queryset.aggregate(total=Sum("amount"))["total"] or Decimal(0)


def confirmed_funded_balance(brand, *, campaign=None) -> Decimal:
    """Stablecoin confirmed and available to fund payouts.

    Unallocated deposits count once, never once per campaign, so a single
    deposit cannot be spent across several campaigns and a brand's balance
    always equals what it actually sent.
    """
    unallocated = _confirmed_total(
        BrandFunding.objects.filter(
            brand=brand, status=FundingStatus.CONFIRMED, campaign__isnull=True
        )
    )
    if campaign is not None:
        # For one campaign: its own allocations plus the shared unallocated
        # pool. Allocations to *other* campaigns stay with those campaigns.
        return _confirmed_total(
            BrandFunding.objects.filter(
                brand=brand, status=FundingStatus.CONFIRMED, campaign=campaign
            )
        ) + unallocated
    return (
        _confirmed_total(
            BrandFunding.objects.filter(
                brand=brand, status=FundingStatus.CONFIRMED, campaign__isnull=False
            )
        )
        + unallocated
    )


def required_campaign_funding(campaign) -> Decimal:
    """Stablecoin a campaign needs on deposit before it may go live.

    Budget is the sum of creator payouts the campaign promises, so the deposit
    required is that budget plus the platform fee. A campaign that is not
    funded cannot be launched: it would accept creators, verify their work, and
    then be unable to pay, which is the failure mode the funding model exists
    to prevent.
    """
    decimals = campaign_token_decimals(campaign)
    return fees.total_cost(campaign.budget, decimals)


def campaign_funding_position(campaign) -> dict:
    """How a campaign is funded versus what it needs."""
    brand = campaign.funding_brand
    required = required_campaign_funding(campaign)
    funded = confirmed_funded_balance(brand) if brand is not None else Decimal(0)
    return {
        "required": str(required),
        "funded": str(funded),
        "shortfall": str(max(Decimal(0), required - funded)),
        "sufficient": funded >= required,
    }


def campaign_token_decimals(campaign) -> int:
    """Precision of the token this campaign pays in.

    Read from the allowlist so fee arithmetic matches the chain. Falls back to
    the platform default only when the token is not registered.
    """
    from apps.blockchain.models import TokenConfig  # noqa: PLC0415 - avoids a cycle

    token = TokenConfig.objects.filter(
        symbol__iexact=campaign.token_symbol, chain_id=campaign.chain_id
    ).first()
    return token.decimals if token else fees.DEFAULT_DECIMALS


def require_campaign_funding(campaign) -> None:
    """Raise unless the campaign's brand has funded its budget plus the fee.

    Called when a campaign goes live. This is the "who provides the money"
    question answered in code rather than in a policy document: a campaign
    cannot accept creators until the brand's confirmed stablecoin covers the
    it promises.
    """
    if campaign.funding_brand is None:
        return  # staff-funded campaign, no brand account to check

    position = campaign_funding_position(campaign)
    if not position["sufficient"]:
        raise RewardEngineError(
            f"Campaign '{campaign.slug}' is not funded. It needs {position['required']} "
            f"{campaign.token_symbol} (budget plus the platform fee) but only "
            f"{position['funded']} is confirmed. Fund the brand, then launch."
        )


def quote_campaign_cost(brand, *, payout_total, decimals=None) -> dict:
    """What a brand must deposit to fund a campaign of this size.

    `payout_total` is the sum of creator payouts the campaign promises (for a
    fixed-rate campaign, reward_rate x expected posts). The 15% fee is added
    on top, exactly as `requiredDeposit` does on chain. A brand is therefore
    never quoted a total the contract would reject as under-funded.

    `decimals` must be the payout token's precision, read from the allowlist.
    Quoting at the wrong precision produces a fee the chain would never
    charge.
    """
    payout_total = Decimal(str(payout_total))
    fee = fees.platform_fee(payout_total, decimals)
    total = payout_total + fee
    funded = confirmed_funded_balance(brand)
    return {
        "payout_total": str(payout_total),
        "platform_fee": str(fee),
        "platform_fee_bps": fees.fee_bps(),
        "total_required": str(total),
        "already_funded": str(funded),
        "shortfall": str(max(Decimal(0), total - funded)),
        "sufficient": funded >= total,
    }
