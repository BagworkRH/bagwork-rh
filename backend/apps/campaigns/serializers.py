"""Campaign API serializers (Spec 02)."""
from rest_framework import serializers

from .models import Campaign, CampaignParticipation


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

    def get_joined(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated and hasattr(request.user, "seller_profile"):
            return obj.participations.filter(seller=request.user.seller_profile).exists()
        return False


class CampaignJoinSerializer(serializers.ModelSerializer):
    """Join/leave result for the current seller."""

    class Meta:
        model = CampaignParticipation
        fields = ("id", "campaign", "seller", "status", "joined_at", "cumulative_reward")
        read_only_fields = ("id", "campaign", "seller", "status", "joined_at", "cumulative_reward")