"""Campaign business logic (eligibility rules, joining)."""
from decimal import Decimal

from django.utils import timezone

from apps.audit.models import AuditLog
from apps.rewards.exceptions import RewardEngineError
from apps.sellers.models import SellerProfile

from .models import Campaign, CampaignParticipation, CampaignStatus, RewardModel


def create_campaign(*, created_by, actor=None, **fields) -> Campaign:
    """Create a campaign, validating the money and the window (Spec 02).

    Rewards are a fixed amount per verified original post, so a campaign whose
    budget cannot cover even one post is worse than useless: it would accept
    creators, verify their work, and then fail to pay. That is checked here
    rather than discovered at payout time.
    """
    # A campaign is funded by the brand that owns it. Derived from the caller
    # rather than accepted from the request body, so a brand cannot attribute a
    # campaign to another brand's money. Staff creating a platform-funded
    # campaign has no brand profile and leaves this null.
    brand = getattr(created_by, "brand_profile", None)
    if brand is not None and not fields.get("funding_brand"):
        fields["funding_brand"] = brand

    _validate_campaign_fields(fields, existing=None)

    # Normalise the money fields before the insert. The API and admin pass
    # Decimals, but this service is also reachable from the shell and tests,
    # where a raw string would otherwise be stored and only fail later inside
    # the reward engine.
    for key in ("budget", "reward_rate", "maximum_reward_per_seller", "remaining_budget"):
        if fields.get(key) is not None and not isinstance(fields[key], Decimal):
            fields[key] = Decimal(str(fields[key]))

    # remaining_budget is NOT NULL, so it must be set at insert time rather than
    # patched afterwards. The reward engine deducts from it transactionally.
    fields.setdefault("remaining_budget", fields.get("budget"))
    campaign = Campaign.objects.create(created_by=created_by, **fields)

    AuditLog.objects.create(
        actor=actor,
        action="CAMPAIGN_CREATED",
        object_type="Campaign",
        object_id=str(campaign.pk),
        metadata={
            "slug": campaign.slug,
            "reward_model": campaign.reward_model,
            "reward_rate": str(campaign.reward_rate),
            "budget": str(campaign.budget),
            "chain_id": campaign.chain_id,
            "created_by": created_by.username,
        },
    )
    return campaign


def update_campaign(campaign, *, actor=None, **fields) -> Campaign:
    """Update a mutable campaign field set, re-validating the money and window.

    Deliberately does not allow editing budget, remaining_budget, chain_id or
    reward_rate once a campaign is live: those are money and settlement
    parameters, and changing them mid-flight would make already-calculated
    rewards irreproducible. Start a new campaign instead.
    """
    locked = {"budget", "remaining_budget", "chain_id", "reward_rate", "created_by"}
    offending = sorted(k for k in fields if k in locked)
    if offending:
        raise RewardEngineError(
            "Cannot change "
            + ", ".join(offending)
            + " on a campaign. These define the payout and settlement terms; "
            "create a new campaign instead."
        )

    if campaign.status == CampaignStatus.ACTIVE and set(fields) - {"status"}:
        raise RewardEngineError(
            "Pause or end the campaign before editing it, so creators are not "
            "promised terms that change under them."
        )

    _validate_campaign_fields(fields, existing=campaign)

    for key, value in fields.items():
        setattr(campaign, key, value)
    campaign.save()

    AuditLog.objects.create(
        actor=actor,
        action="CAMPAIGN_UPDATED",
        object_type="Campaign",
        object_id=str(campaign.pk),
        metadata={"slug": campaign.slug, "fields": sorted(fields.keys())},
    )
    return campaign


def _validate_token_allowed(token_symbol: str, chain_id: int) -> None:
    """The campaign's payout token must be on the chain allowlist.

    A campaign names free text, but the money a creator receives is the token
    the distributor contract actually holds. If those disagree the campaign
    promises a payout the contract cannot deliver, and the failure only
    surfaces at claim time — after the creator has done the work and
    verification has already approved it.

    `chain_id` is part of the check because a symbol can be allowlisted on one
    chain and not another, and a cross-chain mismatch produces the same late
    failure.

    The check is skipped only when there is no allowlist configured for that
    chain at all, which is the state of a fresh development install. It is NOT
    skipped merely because the requested symbol is absent: doing that would let
    any unknown symbol through, defeating the check entirely. Tests and seed
    data therefore register their token on the allowlist rather than relying on
    a bypass.
    """
    from apps.blockchain.models import TokenConfig  # noqa: PLC0415 - avoids a cycle

    configured = TokenConfig.objects.filter(chain_id=int(chain_id))
    if not configured.exists():
        # No allowlist for this chain at all: a fresh install, so there is
        # nothing to validate against.
        return

    if not configured.filter(symbol__iexact=token_symbol).exists():
        allowed = sorted(configured.values_list("symbol", flat=True))
        raise RewardEngineError(
            f"{token_symbol} is not an approved payout token on chain {chain_id}. "
            f"Approved there: {', '.join(allowed)}. Add it to the token allowlist "
            "before creating a campaign that pays in it."
        )


def _validate_campaign_fields(fields, existing=None):
    if "token_symbol" in fields or "chain_id" in fields or existing is None:
        token_symbol = fields.get("token_symbol") or getattr(existing, "token_symbol", None)
        chain_id = fields.get("chain_id") or getattr(existing, "chain_id", None)
        if token_symbol and chain_id:
            _validate_token_allowed(token_symbol, chain_id)
    """Shared validation for create and update."""

    def pick(name, default=None):
        if name in fields:
            return fields[name]
        return getattr(existing, name, default) if existing is not None else default

    def money(name, default=None):
        """Coerce to Decimal.

        Callers reach this from the API (JSON strings), the shell, and the admin
        (all Decimals). Comparing a str to 0 raises TypeError, so the money layer
        must normalise rather than trust the caller.
        """
        value = pick(name, default)
        if value is None or isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (ArithmeticError, ValueError, TypeError) as exc:
            raise RewardEngineError(
                f"{name} must be a number, got {value!r}."
            ) from exc

    reward_model = pick("reward_model")
    if reward_model and reward_model != RewardModel.FIXED:
        raise RewardEngineError(
            "Only FIXED (a fixed reward per verified original post) is available. "
            "Impression- and engagement-based rewards pay for reach that cannot "
            "be independently verified."
        )

    rate = money("reward_rate")
    if rate is not None and rate <= 0:
        raise RewardEngineError("A fixed reward per post must be greater than zero.")

    budget = money("budget")
    if budget is not None and budget <= 0:
        raise RewardEngineError("Campaign budget must be greater than zero.")

    # The budget must cover at least one payout, or a verified creator gets
    # nothing at the end of real work.
    if budget is not None and rate is not None and budget < rate:
        raise RewardEngineError(
            f"Budget ({budget}) is smaller than the per-post reward ({rate}), so "
            "no verified post could ever be paid. Increase the budget or lower the rate."
        )

    start_at = pick("start_at")
    end_at = pick("end_at")
    if start_at and end_at and end_at <= start_at:
        raise RewardEngineError("Campaign end_at must be after start_at.")

    max_reward = money("maximum_reward_per_seller", 0) or 0
    if max_reward and rate is not None and max_reward < rate:
        raise RewardEngineError(
            "maximum_reward_per_seller is below the per-post reward, so a creator "
            "could not be paid for a qualifying post."
        )

    max_rewards = money("maximum_rewards_per_seller", 0) or 0
    if max_rewards and budget is not None and rate is not None and budget > (
        max_rewards * rate
    ):
        raise RewardEngineError(
            "Budget is larger than maximum_rewards_per_seller x reward_rate, so the "
            "surplus could never be paid out. Raise the cap or lower the budget."
        )


def join_campaign(seller, campaign, *, actor=None) -> CampaignParticipation:
    """Validate eligibility and join a campaign (Spec 03).

    Ineligible sellers are rejected with a clear reason. Raises
    RewardEngineError with a user-safe message.
    """
    if seller.status != SellerProfile.Status.ACTIVE:
        raise RewardEngineError("Your seller account is not active.")

    if campaign.status != CampaignStatus.ACTIVE:
        raise RewardEngineError("This campaign is not currently accepting participants.")

    now = timezone.now()
    if now < campaign.start_at:
        raise RewardEngineError(f"This campaign starts on {campaign.start_at.isoformat()}.")
    if now > campaign.end_at:
        raise RewardEngineError("This campaign has ended.")

    req = campaign.requirements_json or {}
    if req.get("minimum_followers"):
        score = seller.reputation_score
        min_followers = int(req.get("minimum_followers"))
        if score < min_followers:
            raise RewardEngineError(
                f"This campaign requires a reputation score of at least {min_followers}."
            )

    participation, created = CampaignParticipation.objects.get_or_create(
        seller=seller, campaign=campaign
    )
    if not created:
        if participation.status == "ACTIVE":
            # Idempotent re-join.
            return participation
        participation.status = "ACTIVE"
        participation.save(update_fields=["status"])

    AuditLog.objects.create(
        actor=actor,
        action="CAMPAIGN_JOINED",
        object_type="Campaign",
        object_id=str(campaign.pk),
        metadata={"seller_code": seller.seller_code, "campaign": campaign.slug},
    )
    return participation


def set_campaign_status(campaign, new_status, reason="", *, actor=None) -> Campaign:
    """Change a campaign's status from the admin back-office (Spec 04 emergency controls).

    Pausing or cancelling a campaign also disables claiming for its rewards
    (enforced in `apps.wallets.services.create_claim`). Every change is audited.
    """
    from django.db import transaction  # noqa: PLC0415 - local import keeps the module import-light

    if new_status not in CampaignStatus.values:
        raise RewardEngineError(
            "status must be one of: " + ", ".join(CampaignStatus.values) + "."
        )

    # A campaign may only go live if the brand behind it has funded the
    # payouts it promises. Without this the platform would take creators'
    # work, verify it, approve it, and then be unable to pay — the exact
    # failure the funding model exists to prevent.
    if new_status == CampaignStatus.ACTIVE:
        from .funding import require_campaign_funding  # noqa: PLC0415 - avoids a cycle

        require_campaign_funding(campaign)

    with transaction.atomic():
        locked = Campaign.objects.select_for_update().get(pk=campaign.pk)
        previous = locked.status
        locked.status = new_status
        locked.save(update_fields=["status", "updated_at"])

    AuditLog.objects.create(
        actor=actor,
        action="CAMPAIGN_STATUS_CHANGED",
        object_type="Campaign",
        object_id=str(locked.pk),
        metadata={
            "slug": locked.slug,
            "from": previous,
            "to": new_status,
            "reason": reason,
        },
    )
    return locked