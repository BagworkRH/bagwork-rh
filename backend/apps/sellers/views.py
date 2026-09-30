"""Views for the authenticated user's own data under /me/."""
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.serializers import UserSerializer
from apps.rewards.exceptions import RewardEngineError
from apps.rewards.models import Reward, RewardStatus
from apps.social.models import PostVerificationStatus, SocialPost
from apps.wallets.models import Claim, Wallet
from apps.wallets.services import (
    create_or_get_wallet,
    verify_wallet_signature,
    wallet_nonce_message,
)

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


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def my_wallets(request):
    """List the user's wallets, or register a new one (POST returns a nonce)."""
    if request.method == "POST":
        address = request.data.get("address", "").strip()
        chain_id = request.data.get("chain_id")
        if not address or not chain_id:
            return Response(
                {"detail": "address and chain_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        seller = getattr(request.user, "seller_profile", None)
        if seller is None:
            return Response(
                {"detail": "Seller profile required."}, status=status.HTTP_400_BAD_REQUEST
            )
        wallet = create_or_get_wallet(seller, address, int(chain_id), actor=request.user)
        return Response(
            {
                "id": wallet.id,
                "address": wallet.address,
                "chain_id": wallet.chain_id,
                "wallet_type": wallet.wallet_type,
                "verified": wallet.verified,
                "nonce": wallet.nonce,
                # The exact string the wallet must sign; the frontend passes it
                # straight to personal_sign.
                "message": wallet_nonce_message(wallet),
                "connected_at": wallet.connected_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )

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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def wallet_verify(request, pk):
    """Verify wallet ownership from a signed nonce (Spec 04).

    Body: {"signature": "0x..."} where the signature is `personal_sign` over
    the exact `message` returned by POST /me/wallets/.

    Ownership is proven cryptographically: the address alone is never trusted,
    and the nonce is single-use (cleared once verification succeeds).
    """
    seller = getattr(request.user, "seller_profile", None)
    if seller is None:
        return Response({"detail": "Seller profile required."}, status=status.HTTP_400_BAD_REQUEST)

    wallet = get_object_or_404(Wallet, pk=pk, seller=seller)
    signature = (request.data.get("signature") or "").strip()
    if not signature:
        return Response(
            {"detail": "signature is required."}, status=status.HTTP_400_BAD_REQUEST
        )
    if not wallet.nonce:
        return Response(
            {"detail": "No pending verification for this wallet. Re-register it to get a nonce."},
            status=status.HTTP_409_CONFLICT,
        )

    try:
        wallet = verify_wallet_signature(wallet, signature, actor=request.user)
    except RewardEngineError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            "id": wallet.id,
            "address": wallet.address,
            "chain_id": wallet.chain_id,
            "wallet_type": wallet.wallet_type,
            "verified": wallet.verified,
            "connected_at": wallet.connected_at.isoformat(),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_posts(request):
    """The signed-in creator's own posts, newest first.

    Scoped to the requesting seller: a creator can see their own post status
    and, when a post was rejected, why -- they need that in order to fix it.
    They can never see another seller's posts. This is the creator-facing
    replacement for the now staff-only `GET /api/v1/posts/`.
    """
    profile = getattr(request.user, "seller_profile", None)
    if profile is None:
        return Response({"detail": "No seller profile."}, status=status.HTTP_404_NOT_FOUND)

    qs = SocialPost.objects.filter(seller=profile).order_by("-discovered_at")
    status_param = request.query_params.get("status")
    if status_param:
        qs = qs.filter(verification_status=status_param)
    return Response([_my_post_payload(p) for p in qs[:100]])


def _my_post_payload(post):
    """A creator-facing post view.

    Deliberately excludes nothing the creator is entitled to see about their own
    content, and exposes nothing about other sellers.
    """
    return {
        "id": post.pk,
        "platform": post.platform,
        "external_post_id": post.external_post_id,
        "post_url": post.post_url,
        "campaign": post.campaign.slug if post.campaign else None,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "verification_status": post.verification_status,
        "rejection_reason": post.rejection_reason,
        "is_original": post.is_original,
        "originality_evidence": post.originality_evidence,
        "impressions": post.impressions,
        "likes": post.likes,
        "reposts": post.reposts,
        "replies": post.replies,
        "total_engagement": post.total_engagement,
    }


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