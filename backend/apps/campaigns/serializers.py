"""Campaign API serializers (Spec 02)."""
from rest_framework import serializers

from apps.rewards.exceptions import RewardEngineError

from .models import Campaign, CampaignParticipation, RewardModel


class CampaignSerializer(serializers.ModelSerializer):
    remaining_budget = serializers.DecimalField(max_digits=40, decimal_places=18, read_only=True)
    joined = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "project_name",
            "token_symbol",
            "chain_id",
            "budget",
            "remaining_budget",
            "reward_model",
            "reward_rate",
            "maximum_reward_per_seller",
            "maximum_rewards_per_seller",
            "start_at",
            "end_at",
            "status",
            "requirements_json",
            "joined",
            "created_at",
        )
        read_only_fields = ("status", "remaining_budget", "created_at")

    def validate_reward_model(self, value):
        """Only fixed-per-verified-original-post is offered at launch.

        The engine can still compute impression- and engagement-based rewards,
        but they are not selectable: those models pay for reach we cannot
        verify, which would undercut the auditability the platform is built on.
        Re-enabling them is a deliberate, later decision.
        """
        if value != RewardModel.FIXED:
            raise serializers.ValidationError(
                "Only FIXED (a fixed reward per verified original post) is available "
                "at launch. Rewards are paid for original, disclosed posts, not for "
                "impressions or engagement, because those cannot be independently "
                "verified on every platform."
            )
        return value

    def validate(self, attrs):
        """A fixed reward model needs a positive fixed rate."""
        model = attrs.get("reward_model") or getattr(self.instance, "reward_model", None)
        rate = attrs.get("reward_rate", getattr(self.instance, "reward_rate", None))
        if model == RewardModel.FIXED and (rate is None or rate <= 0):
            raise serializers.ValidationError(
                {"reward_rate": "A fixed reward per post must be greater than zero."}
            )
        return attrs

    def get_joined(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated and hasattr(request.user, "seller_profile"):
            return obj.participations.filter(seller=request.user.seller_profile).exists()
        return False


class CampaignWriteSerializer(serializers.ModelSerializer):
    """Create/update payload for a campaign (staff-only).

    Separate from the read serializer on purpose: the public one hides
    `remaining_budget` and never accepts writes, while this one owns the
    campaign's money and window rules.
    """

    class Meta:
        model = Campaign
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "project_name",
            "token_symbol",
            "chain_id",
            "budget",
            "reward_model",
            "reward_rate",
            "maximum_reward_per_seller",
            "maximum_rewards_per_seller",
            "start_at",
            "end_at",
            "requirements_json",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        from apps.campaigns.services import _validate_campaign_fields  # noqa: PLC0415

        # Model-level rules (fixed-only, budget covers one payout, window order)
        # live in the service so the shell and admin paths are held to the same.
        # The service raises a domain error; a serializer must turn that into a
        # 400 with a readable message rather than let it escape as a 500.
        try:
            _validate_campaign_fields(dict(attrs), existing=self.instance)
        except RewardEngineError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return attrs


class CampaignJoinSerializer(serializers.ModelSerializer):
    """Join/leave result for the current seller."""

    class Meta:
        model = CampaignParticipation
        fields = ("id", "campaign", "seller", "status", "joined_at", "cumulative_reward")
        read_only_fields = ("id", "campaign", "seller", "status", "joined_at", "cumulative_reward")