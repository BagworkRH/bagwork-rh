"""Serializers for seller profile and dashboard endpoints under /me/."""
from rest_framework import serializers

from apps.accounts.serializers import UserSerializer

from .models import SellerProfile


class SellerProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = SellerProfile
        fields = (
            "id",
            "user",
            "seller_code",
            "display_name",
            "status",
            "reputation_score",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "seller_code", "status", "reputation_score", "created_at", "updated_at")


class SellerDashboardSerializer(serializers.Serializer):
    """Dashboard summary for the seller home screen (Spec 01)."""

    seller = SellerProfileSerializer(read_only=True)
    total_earnings = serializers.DecimalField(max_digits=40, decimal_places=18)
    available_to_claim = serializers.DecimalField(max_digits=40, decimal_places=18)
    pending_rewards = serializers.IntegerField()
    posts_tracked = serializers.IntegerField()
    verified_posts = serializers.IntegerField()
    total_engagement = serializers.IntegerField()