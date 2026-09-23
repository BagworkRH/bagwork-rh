"""Reward engine (Spec 03).

The server alone determines rewards. Inputs:
  - campaign
  - post
  - metric snapshot
  - seller
  - current campaign budget
  - seller reward history

Output:
  - gross reward
  - deductions/exclusions
  - final reward
  - calculation version
  - explanation

Everything must be deterministic and reproducible from saved inputs.
Money uses Decimal exclusively; no floats in financial math.
"""
from dataclasses import dataclass
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.campaigns.models import Campaign, RewardModel
from apps.rewards.models import Reward, RewardCalculationVersion, RewardStatus
from apps.social.models import PostVerificationStatus

from .exceptions import RewardEngineError

CALCULATION_VERSION = RewardCalculationVersion.V1
ZERO = Decimal("0")
TOKEN_PRECISION = Decimal("0.000000000000000001")  # 18 decimals
_COUNTED_STATUSES = (
    RewardStatus.VERIFIED,
    RewardStatus.APPROVED,
    RewardStatus.AVAILABLE,
    RewardStatus.CLAIMED,
)
_LIVE_STATUSES = (
    RewardStatus.PENDING,
    RewardStatus.VERIFIED,
    RewardStatus.APPROVED,
    RewardStatus.AVAILABLE,
)


@dataclass
class RewardResult:
    gross: Decimal
    deductions: Decimal
    final_amount: Decimal
    calculation_version: str
    explanation: str


def _metric_value(post_or_snapshot, field):
    """Fetch a metric value from either a model instance or a dict snapshot."""
    if isinstance(post_or_snapshot, dict):
        value = post_or_snapshot.get(field, 0)
    else:
        value = getattr(post_or_snapshot, field, 0)
    if value in (None, ""):
        return ZERO
    return Decimal(str(value))


def _impressions(post_or_snapshot):
    """Best available impression count from the latest snapshot or the post."""
    return _metric_value(post_or_snapshot, "impressions")


def _engagements(post_or_snapshot):
    return (
        _metric_value(post_or_snapshot, "likes")
        + _metric_value(post_or_snapshot, "reposts")
        + _metric_value(post_or_snapshot, "replies")
    )


def compute_raw_reward(campaign, post, snapshot=None) -> RewardResult:
    """Compute the deterministic gross/final reward for a verified post.

    Pure calculation: no DB writes. Callers persist the result inside a
    transaction with proper locks.
    """
    impressions = _impressions(snapshot or post)
    engagements = _engagements(snapshot or post)

    model = campaign.reward_model
    rate = campaign.reward_rate

    if model == RewardModel.FIXED:
        gross = rate
        explanation = f"Fixed reward: {rate} {campaign.token_symbol} per verified post."
    elif model == RewardModel.IMPRESSION_BASED:
        gross = (impressions / Decimal("1000")) * rate
        explanation = (
            f"Impression-based: {int(impressions // 1000)} * 1000 impressions "
            f"* {rate} per 1k = {gross} {campaign.token_symbol}."
        )
    elif model == RewardModel.ENGAGEMENT_BASED:
        gross = (engagements / Decimal("100")) * rate
        explanation = (
            f"Engagement-based: {engagements} engagements / 100 * {rate} = "
            f"{gross} {campaign.token_symbol}."
        )
    elif model == RewardModel.HYBRID:
        fixed = rate
        engagement_rate = Decimal(
            str(campaign.requirements_json.get("engagement_rate", 0))
        ) or ZERO
        engagement_component = (engagements / Decimal("100")) * engagement_rate
        gross = fixed + engagement_component
        explanation = (
            f"Hybrid: fixed {fixed} + engagement component {engagement_component} = "
            f"{gross} {campaign.token_symbol}."
        )
    else:  # pragma: no cover - guarded by model validation
        raise RewardEngineError(f"Unknown reward model: {model}")

    gross = gross.quantize(TOKEN_PRECISION)
    return RewardResult(
        gross=gross,
        deductions=ZERO,
        final_amount=gross,
        calculation_version=CALCULATION_VERSION,
        explanation=explanation,
    )
def apply_caps(campaign, seller, post, snapshot=None) -> RewardResult:
    """Apply caps to the raw calculation.

    Enforces:
      - per-post cap  (requirements_json["maximum_reward_per_post"])
      - per-seller cap (campaign.maximum_reward_per_seller)
    (the remaining-budget cap is applied by `calculate_reward` under lock).
    """
    result = compute_raw_reward(campaign, post, snapshot)
    amount = result.gross

    per_post_cap = Decimal(str(campaign.requirements_json.get("maximum_reward_per_post", 0)) or 0)
    if per_post_cap > 0 and amount > per_post_cap:
        amount = per_post_cap

    per_seller_cap = campaign.maximum_reward_per_seller if campaign.maximum_reward_per_seller else ZERO
    if per_seller_cap > 0:
        earned = Reward.objects.filter(
            seller=seller,
            campaign=campaign,
            status__in=_COUNTED_STATUSES,
        ).aggregate(total=models.Sum("amount"))["total"] or ZERO
        remaining_for_seller = per_seller_cap - earned
        if remaining_for_seller <= 0:
            raise RewardEngineError(
                f"Seller {seller.seller_code} has reached the per-seller cap "
                f"of {per_seller_cap} {campaign.token_symbol}."
            )
        amount = min(amount, remaining_for_seller)

    result.deductions = result.gross - amount
    result.final_amount = amount
    result.explanation += f" After caps: final {amount} {campaign.token_symbol}."
    return result


def calculate_reward(campaign, post, seller, snapshot=None, *, user=None) -> Reward:
    """Persist a calculated reward for a verified post (Spec 03 lifecycle).

    Steps:
      1. Validate post status is VERIFIED.
      2. Deterministically compute the amount (never trusting the client).
      3. Lock the campaign budget row and check remaining budget.
      4. Create the Reward row (PENDING) inside the same transaction.
      5. Reserve the amount from the campaign budget.
    """
    if post.verification_status != PostVerificationStatus.VERIFIED:
        raise RewardEngineError("Post must be VERIFIED before a reward can be calculated.")

    result = apply_caps(campaign, seller, post, snapshot)

    if result.final_amount <= 0:
        raise RewardEngineError("Calculated reward is zero; no reward created.")

    with transaction.atomic():
        # Row lock on the campaign budget prevents races (Spec 03).
        locked_campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)

        existing = Reward.objects.filter(
            post=post,
            status__in=_LIVE_STATUSES,
        ).first()
        if existing:
            raise RewardEngineError("A reward already exists for this post.")

        if locked_campaign.remaining_budget < result.final_amount:
            raise RewardEngineError(
                f"Campaign budget remaining ({locked_campaign.remaining_budget}) "
                f"is insufficient for reward {result.final_amount}."
            )

        reward = Reward.objects.create(
            seller=seller,
            campaign=locked_campaign,
            post=post,
            amount=result.final_amount,
            gross_amount=result.gross,
            deduction_amount=result.deductions,
            currency=campaign.requirements_json.get("currency", "USDT"),
            token_symbol=locked_campaign.token_symbol,
            chain_id=locked_campaign.chain_id,
            calculation_version=result.calculation_version,
            explanation=result.explanation,
            status=RewardStatus.PENDING,
        )

        locked_campaign.remaining_budget -= result.final_amount
        locked_campaign.save(update_fields=["remaining_budget", "updated_at"])

        AuditLog.objects.create(
            actor=user,
            action="REWARD_CALCULATED",
            object_type="Reward",
            object_id=str(reward.pk),
            metadata={
                "amount": str(reward.amount),
                "gross": str(reward.gross_amount),
                "deductions": str(reward.deduction_amount),
                "calculation_version": str(reward.calculation_version),
                "campaign_id": campaign.pk,
                "post_id": post.pk,
                "seller_code": seller.seller_code,
            },
        )

        from apps.blockchain.ledger import record  # noqa: PLC0415 - lazy: avoids an import cycle
        from apps.blockchain.models import LedgerAction  # noqa: PLC0415 - lazy import

        record(
            LedgerAction.REWARD_EARNED,
            seller=seller,
            reward=reward,
            token_symbol=reward.token_symbol,
            amount=reward.amount,
            amount_smallest_unit=0,
        )

    return reward


def approve_reward(reward, *, actor=None) -> Reward:
    """Approve a reward: PENDING -> APPROVED with budget already reserved.

    Idempotent: approving an already-approved reward is a no-op.
    """
    with transaction.atomic():
        locked = Reward.objects.select_for_update().get(pk=reward.pk)
        if locked.status in (RewardStatus.APPROVED, RewardStatus.AVAILABLE):
            return locked  # idempotent
        if locked.status != RewardStatus.PENDING:
            raise RewardEngineError(f"Cannot approve reward in state {locked.status}.")

        locked.status = RewardStatus.APPROVED
        locked.approved_at = timezone.now()
        locked.save(update_fields=["status", "approved_at"])
        AuditLog.objects.create(
            actor=actor,
            action="REWARD_APPROVED",
            object_type="Reward",
            object_id=str(locked.pk),
            metadata={"amount": str(locked.amount), "seller_code": locked.seller.seller_code},
        )

        # Ledger entry (Spec 04): the platform now owes this seller money.
        from apps.blockchain.ledger import record  # noqa: PLC0415 - lazy: avoids an import cycle
        from apps.blockchain.models import LedgerAction  # noqa: PLC0415 - lazy import

        record(
            LedgerAction.REWARD_APPROVED,
            seller=locked.seller,
            reward=locked,
            token_symbol=locked.token_symbol,
            amount=locked.amount,
        )
    return locked


def make_available(reward, *, actor=None) -> Reward:
    """Move an APPROVED reward to AVAILABLE (claimable)."""
    with transaction.atomic():
        locked = Reward.objects.select_for_update().get(pk=reward.pk)
        if locked.status == RewardStatus.AVAILABLE:
            return locked
        if locked.status != RewardStatus.APPROVED:
            raise RewardEngineError(f"Cannot make reward available in state {locked.status}.")
        locked.status = RewardStatus.AVAILABLE
        locked.save(update_fields=["status"])
        AuditLog.objects.create(
            actor=actor,
            action="REWARD_AVAILABLE",
            object_type="Reward",
            object_id=str(locked.pk),
            metadata={"amount": str(locked.amount), "seller_code": locked.seller.seller_code},
        )
    return locked


def reverse_reward(reward, reason, *, actor=None) -> Reward:
    """Reverse a reward and restore the budget (Spec 03: never silently modify)."""
    if not reason:
        raise RewardEngineError("A reversal reason is required.")
    with transaction.atomic():
        locked = Reward.objects.select_for_update().get(pk=reward.pk)
        if locked.status == RewardStatus.REVERSED:
            return locked  # idempotent
        if locked.status in (RewardStatus.CLAIMED,):
            raise RewardEngineError("Cannot reverse a claimed reward through this flow.")

        # Restore budget for not-yet-claimed rewards.
        campaign = Campaign.objects.select_for_update().get(pk=locked.campaign.pk)
        campaign.remaining_budget += locked.amount
        campaign.save(update_fields=["remaining_budget", "updated_at"])

        locked.status = RewardStatus.REVERSED
        locked.reversal_reason = reason
        locked.save(update_fields=["status", "reversal_reason"])
        AuditLog.objects.create(
            actor=actor,
            action="REWARD_REVERSED",
            object_type="Reward",
            object_id=str(locked.pk),
            metadata={"reason": reason, "amount": str(locked.amount)},
        )
    return locked
