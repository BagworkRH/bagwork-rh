"""Posts API views (Spec 02): list, detail, submit, spare admin endpoints."""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.campaigns.models import Campaign
from apps.rewards.exceptions import RewardEngineError
from apps.rewards.services import calculate_reward

from .models import SocialPost
from .post_services import create_post_from_provider, run_verification


def _post_payload(post):
    snap = post.metric_snapshots.order_by("-collected_at").first()
    return {
        "id": post.pk,
        "external_post_id": post.external_post_id,
        "post_url": post.post_url,
        "campaign": post.campaign.slug if post.campaign else None,
        "seller_code": post.seller.seller_code,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "verification_status": post.verification_status,
        "rejection_reason": post.rejection_reason,
        "impressions": snap.impressions if snap else post.impressions,
        "likes": snap.likes if snap else post.likes,
        "reposts": snap.reposts if snap else post.reposts,
        "replies": snap.replies if snap else post.replies,
        "last_metrics_sync": post.last_metrics_sync.isoformat() if post.last_metrics_sync else None,
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def post_list(request):
    """List posts (optionally filter by campaign/seller/status)."""
    qs = SocialPost.objects.all().order_by("-discovered_at")
    campaign = request.query_params.get("campaign")
    seller = request.query_params.get("seller")
    status_param = request.query_params.get("status")
    if campaign:
        qs = qs.filter(campaign__slug=campaign)
    if seller:
        qs = qs.filter(seller__seller_code=seller)
    if status_param:
        qs = qs.filter(verification_status=status_param)
    return Response([_post_payload(p) for p in qs[:100]])


@api_view(["GET"])
@permission_classes([AllowAny])
def post_detail(request, pk):
    post = get_object_or_404(SocialPost, pk=pk)
    return Response(_post_payload(post))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def post_submit(request):
    """Submit a post URL for tracking (seller-only for their own posts).

    In production the provider discovery flow feeds this service; the manual
    submit endpoint exists for testing the pipeline end-to-end.
    """
    try:
        seller = request.user.seller_profile
    except Exception:
        return Response({"detail": "Seller profile required."}, status=status.HTTP_400_BAD_REQUEST)

    campaign_slug = request.data.get("campaign")
    if not campaign_slug:
        return Response({"detail": "campaign (slug) is required."}, status=status.HTTP_400_BAD_REQUEST)
    campaign = Campaign.objects.filter(slug=campaign_slug).first()
    if campaign is None:
        return Response({"detail": "Unknown campaign."}, status=status.HTTP_404_NOT_FOUND)

    payload = {
        "post_id": str(request.data.get("external_post_id", "")).strip(),
        "text": request.data.get("text", ""),
        "created_at": request.data.get("published_at") or None,
        "post_url": request.data.get("post_url", ""),
    }
    if not payload["post_id"]:
        return Response({"detail": "external_post_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    existing = SocialPost.objects.filter(external_post_id=payload["post_id"]).first()
    if existing:
        return Response(
            {"detail": "Duplicate post; already tracked.", "post": _post_payload(existing)},
            status=status.HTTP_409_CONFLICT,
        )

    post = create_post_from_provider(seller, campaign, payload, actor=request.user)
    return Response(_post_payload(post), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def post_verify(request, pk):
    """Advance a single post one step via the verification pipeline.

    DEVELOPMENT MOCK SURFACE: manual trigger for testing. In production this is
    driven by Celery discovery/metadata tasks.
    """
    post = get_object_or_404(SocialPost, pk=pk)
    try:
        post = run_verification(post, actor=request.user)
    except RewardEngineError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(_post_payload(post))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def post_calculate_reward(request, pk):
    """Calculate a reward for a verified post (server-side determination)."""
    post = get_object_or_404(SocialPost, pk=pk)
    snapshot = post.metric_snapshots.order_by("collected_at").last()
    snapshot_data = (
        {
            "impressions": snapshot.impressions,
            "likes": snapshot.likes,
            "reposts": snapshot.reposts,
            "replies": snapshot.replies,
            "quotes": snapshot.quotes,
            "bookmarks": snapshot.bookmarks,
            "collected_at": snapshot.collected_at,
        }
        if snapshot
        else None
    )
    try:
        reward = calculate_reward(
            post.campaign, post, post.seller, snapshot_data, user=request.user
        )
    except RewardEngineError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {
            "reward_id": reward.pk,
            "amount": str(reward.amount),
            "gross": str(reward.gross_amount),
            "deductions": str(reward.deduction_amount),
            "status": reward.status,
            "calculation_version": reward.calculation_version,
            "explanation": reward.explanation,
        },
        status=status.HTTP_201_CREATED,
    )