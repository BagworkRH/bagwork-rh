"""Views for the authenticated user's own data under /me/."""
from django.db.models import Sum
from django.db.models.functions import Coalesce
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.serializers import UserSerializer
from apps.rewards.models import Reward, RewardStatus
from apps.social.models import PostVerificationStatus, SocialPost
from apps.wallets.models import Claim, Wallet

from .models import SellerProfile
from .serializers import SellerDashboardSerializer, SellerProfileSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


@api_view(["GET", "POST", "PATCH"])
@permission_classes([IsAuthenticated])
def seller_profile(request):
    profile, created = SellerProfile.objects.get_or_create(user=request.user)
    if request.method == "GET":
        return Response(SellerProfileSerializer(profile).data)
    if request.method == "POST":
        # Idempotent onboard: update profile if it exists, create otherwise.
        serializer = SellerProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
    serializer = SellerProfileSerializer(profile, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_wallets(request):
    wallets = Wallet.objects.filter(seller__user=request.user)
    return Response(
        [
            {
                "id": w.id,
                "address": w.address,
                "chain_id": w.chain_id,
                "wallet_type": w.wallet_type,
                "verified": w.verified,
                "connected_at": w.connected_at.isoformat(),
            }
            for w in wallets
        ]
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_rewards(request):
    rewards = Reward.objects.filter(seller__user=request.user).order_by("-created_at")
    return Response(
        [
            {
                "id": r.id,
                "campaign": r.campaign.name if r.campaign else None,
                "amount": str(r.amount),
                "token": r.token_symbol,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
            }
            for r in rewards
        ]
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_claims(request):
    claims = Claim.objects.filter(seller__user=request.user).order_by("-created_at")
    return Response(
        [
            {
                "id": c.id,
                "wallet": c.wallet.address,
                "amount": str(c.amount),
                "token": c.token_symbol,
                "status": c.status,
                "transaction_hash": c.transaction_hash,
                "created_at": c.created_at.isoformat(),
            }
            for c in claims
        ]
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    """Aggregate the seller dashboard summary (Spec 01)."""
    user = request.user
    if not hasattr(user, "seller_profile"):
        return Response({"detail": "No seller profile."}, status=status.HTTP_404_NOT_FOUND)
    profile = user.seller_profile

    rewards = Reward.objects.filter(seller=profile)

    total_earnings = rewards.aggregate(total=Coalesce(Sum("amount"), 0))["total"]
    available = rewards.filter(status=RewardStatus.AVAILABLE).aggregate(
        total=Coalesce(Sum("amount"), 0)
    )["total"]
    pending_count = rewards.filter(status=RewardStatus.PENDING).count()

    posts = SocialPost.objects.filter(seller=profile)
    posts_tracked = posts.count()
    verified_posts = posts.filter(verification_status=PostVerificationStatus.VERIFIED).count()

    total_engagement = posts.aggregate(total=Coalesce(Sum("total_engagement"), 0))["total"]

    data = {
        "seller": SellerProfileSerializer(profile).data,
        "total_earnings": total_earnings,
        "available_to_claim": available,
        "pending_rewards": pending_count,
        "posts_tracked": posts_tracked,
        "verified_posts": verified_posts,
        "total_engagement": total_engagement,
    }
    return Response(SellerDashboardSerializer(data).data)