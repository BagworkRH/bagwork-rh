"""Staff-only back-office API (Spec 05 Phase 7 · Spec 01 "Admin UI").

The Django admin is the primary admin interface (see `apps.*.admin`); this API
backs a custom admin UI / automation and exposes the same operations, always
through the service layer so every action is audited:

  GET  /api/v1/admin/overview/                 platform statistics
  GET  /api/v1/admin/sellers/                  seller directory
  POST /api/v1/admin/sellers/<id>/status/      activate / suspend a seller
  GET  /api/v1/admin/campaigns/                campaign directory
  POST /api/v1/admin/campaigns/<id>/status/    pause / cancel a campaign
  GET  /api/v1/admin/posts/                    post review queue
  POST /api/v1/admin/posts/<id>/review/        approve / reject a post
  GET  /api/v1/admin/rewards/                  reward review queue
  POST /api/v1/admin/rewards/<id>/review/      approve / make available / reverse
  GET  /api/v1/admin/claims/                   claim directory
  POST /api/v1/admin/claims/<id>/fail/         mark a claim failed (with reason)
  GET  /api/v1/admin/risk/                     fraud/risk review queue
  POST /api/v1/admin/risk/<id>/resolve/        dismiss / confirm a risk flag
  GET  /api/v1/admin/audit-logs/               append-only audit trail
  GET  /api/v1/admin/settings/                 platform controls / token allowlist

Access is restricted to staff users (`IsAdminUser`). Nothing here is public, and
no endpoint accepts an amount supplied by the client.
"""
from datetime import timedelta

from django.conf import settings
from django.db.models import DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.blockchain.models import PlatformControl, TokenConfig
from apps.campaigns.models import Campaign
from apps.rewards.exceptions import RewardEngineError
from apps.rewards.models import Reward
from apps.social.models import SocialPost
from apps.wallets.models import Claim

from . import risk
from .models import AuditLog, RiskFlag, RiskStatus

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def _page(queryset, request):
    """Small explicit pagination slice (function-based views, Spec 02 pagination)."""
    try:
        limit = int(request.query_params.get("limit", DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        limit = DEFAULT_PAGE_SIZE
    try:
        offset = int(request.query_params.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    offset = max(0, offset)
    total = queryset.count()
    return {
        "count": total,
        "limit": limit,
        "offset": offset,
        "results": list(queryset[offset : offset + limit]),
    }


def seller_to_dict(profile) -> dict:
    return {
        "id": profile.pk,
        "seller_code": profile.seller_code,
        "display_name": profile.display_name,
        "email": profile.user.email,
        "username": profile.user.username,
        "status": profile.status,
        "reputation_score": profile.reputation_score,
        "wallets": profile.wallets.count(),
        "verified_wallets": profile.wallets.filter(verified=True).count(),
        "social_accounts": profile.social_accounts.count(),
        "posts": profile.posts.count(),
        "created_at": profile.created_at.isoformat(),
    }


def campaign_to_dict(campaign) -> dict:
    return {
        "id": campaign.pk,
        "name": campaign.name,
        "slug": campaign.slug,
        "project_name": campaign.project_name,
        "status": campaign.status,
        "reward_model": campaign.reward_model,
        "reward_rate": str(campaign.reward_rate),
        "token_symbol": campaign.token_symbol,
        "chain_id": campaign.chain_id,
        "budget": str(campaign.budget),
        "remaining_budget": str(campaign.remaining_budget),
        "participants": campaign.participations.count(),
        "rewards": campaign.rewards.count(),
        "start_at": campaign.start_at.isoformat(),
        "end_at": campaign.end_at.isoformat(),
        "created_at": campaign.created_at.isoformat(),
    }


def post_to_dict(post) -> dict:
    return {
        "id": post.pk,
        "external_post_id": post.external_post_id,
        "post_url": post.post_url,
        "seller_code": post.seller.seller_code,
        "campaign": post.campaign.slug if post.campaign_id else None,
        "verification_status": post.verification_status,
        "rejection_reason": post.rejection_reason,
        "impressions": post.impressions,
        "likes": post.likes,
        "reposts": post.reposts,
        "replies": post.replies,
        "total_engagement": post.total_engagement,
        "published_at": post.published_at.isoformat(),
        "last_metrics_sync": post.last_metrics_sync.isoformat() if post.last_metrics_sync else None,
        "has_reward": hasattr(post, "reward"),
    }


def reward_to_dict(reward) -> dict:
    return {
        "id": reward.pk,
        "seller_code": reward.seller.seller_code,
        "campaign": reward.campaign.slug,
        "post": reward.post_id,
        "amount": str(reward.amount),
        "gross_amount": str(reward.gross_amount),
        "deduction_amount": str(reward.deduction_amount),
        "token_symbol": reward.token_symbol,
        "chain_id": reward.chain_id,
        "status": reward.status,
        "explanation": reward.explanation,
        "reversal_reason": reward.reversal_reason,
        "created_at": reward.created_at.isoformat(),
        "approved_at": reward.approved_at.isoformat() if reward.approved_at else None,
    }


def claim_to_dict(claim) -> dict:
    return {
        "id": claim.pk,
        "seller_code": claim.seller.seller_code,
        "wallet": claim.wallet.address,
        "reward": claim.reward_id,
        "amount": str(claim.amount),
        "amount_smallest_unit": claim.amount_smallest_unit,
        "token_symbol": claim.token_symbol,
        "chain_id": claim.chain_id,
        "status": claim.status,
        "transaction_hash": claim.transaction_hash,
        "failure_reason": claim.failure_reason,
        "created_at": claim.created_at.isoformat(),
        "expired_at": claim.expired_at.isoformat() if claim.expired_at else None,
        "confirmed_at": claim.confirmed_at.isoformat() if claim.confirmed_at else None,
    }


def _error(message):
    """Uniform error shape for the back-office API."""
    return Response({"detail": str(message)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def overview(request):
    """Admin overview: platform statistics (Spec 01 §Admin UI "Overview")."""
    from apps.sellers.models import SellerProfile  # noqa: PLC0415 - lazy import

    recent = timezone.now() - timedelta(hours=24)
    rewards = Reward.objects.all()
    claims = Claim.objects.all()
    return Response(
        {
            "generated_at": timezone.now().isoformat(),
            "sellers": {
                "total": SellerProfile.objects.count(),
                "active": SellerProfile.objects.filter(status="ACTIVE").count(),
                "suspended": SellerProfile.objects.filter(status="SUSPENDED").count(),
                "new_last_24h": SellerProfile.objects.filter(created_at__gte=recent).count(),
            },
            "campaigns": {
                "total": Campaign.objects.count(),
                "active": Campaign.objects.filter(status="ACTIVE").count(),
                "paused": Campaign.objects.filter(status="PAUSED").count(),
                "ended": Campaign.objects.filter(status="ENDED").count(),
                "budget": str(
                    Campaign.objects.aggregate(
                        t=Coalesce(
                            Sum("budget"), 0, output_field=DecimalField(max_digits=40, decimal_places=18)
                        )
                    )["t"]
                ),
                "remaining_budget": str(
                    Campaign.objects.aggregate(
                        t=Coalesce(
                            Sum("remaining_budget"),
                            0,
                            output_field=DecimalField(max_digits=40, decimal_places=18),
                        )
                    )["t"]
                ),
            },
            "posts": {
                "total": SocialPost.objects.count(),
                "verified": SocialPost.objects.filter(verification_status="VERIFIED").count(),
                "awaiting_metrics": SocialPost.objects.filter(
                    verification_status="METRICS_PENDING"
                ).count(),
                "flagged": SocialPost.objects.filter(
                    verification_status="SUSPICIOUS_ACTIVITY"
                ).count(),
            },
            "rewards": {
                "pending_review": rewards.filter(status="PENDING").count(),
                "approved": rewards.filter(status="APPROVED").count(),
                "available": rewards.filter(status="AVAILABLE").count(),
                "claimed": rewards.filter(status="CLAIMED").count(),
                "reversed": rewards.filter(status="REVERSED").count(),
                "total_amount": str(
                    rewards.aggregate(
                        t=Coalesce(
                            Sum("amount"), 0, output_field=DecimalField(max_digits=40, decimal_places=18)
                        )
                    )["t"]
                ),
            },
            "claims": {
                "open": claims.filter(
                    status__in=["CREATED", "SIGNING", "SUBMITTED", "PENDING"]
                ).count(),
                "confirmed": claims.filter(status="CONFIRMED").count(),
                "failed": claims.filter(status="FAILED").count(),
                "expired": claims.filter(status="EXPIRED").count(),
            },
            "risk": risk.queue_summary(),
            "audit_events_last_24h": AuditLog.objects.filter(created_at__gte=recent).count(),
        }
    )


@api_view(["GET"])
@permission_classes([IsAdminUser])
def sellers(request):
    """Seller directory with status/search filters (Spec 01 §Admin UI "Sellers")."""
    from apps.sellers.models import SellerProfile  # noqa: PLC0415 - lazy import

    queryset = SellerProfile.objects.select_related("user").order_by("-created_at")
    seller_status = request.query_params.get("status")
    if seller_status:
        queryset = queryset.filter(status=seller_status.upper())
    search = request.query_params.get("search")
    if search:
        queryset = queryset.filter(
            Q(seller_code__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__username__icontains=search)
        )
    page = _page(queryset, request)
    page["results"] = [seller_to_dict(p) for p in page["results"]]
    return Response(page)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def seller_status(request, pk):
    """Activate / suspend a seller (audited; financial history untouched)."""
    from apps.sellers.models import SellerProfile  # noqa: PLC0415 - lazy import
    from apps.sellers.services import set_seller_status  # noqa: PLC0415 - lazy import

    profile = get_object_or_404(SellerProfile, pk=pk)
    try:
        profile = set_seller_status(
            profile,
            request.data.get("status", ""),
            request.data.get("reason", ""),
            actor=request.user,
        )
    except RewardEngineError as exc:
        return _error(exc)
    return Response(seller_to_dict(profile))


@api_view(["GET"])
@permission_classes([IsAdminUser])
def campaigns(request):
    """Campaign directory (Spec 01 §Admin UI "Campaigns")."""
    queryset = Campaign.objects.select_related("created_by").order_by("-created_at")
    campaign_status = request.query_params.get("status")
    if campaign_status:
        queryset = queryset.filter(status=campaign_status.upper())
    search = request.query_params.get("search")
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(slug__icontains=search))
    page = _page(queryset, request)
    page["results"] = [campaign_to_dict(c) for c in page["results"]]
    return Response(page)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def campaign_status(request, pk):
    """Pause / resume / end / cancel a campaign (audited; Spec 04 controls)."""
    from apps.campaigns.services import set_campaign_status  # noqa: PLC0415 - lazy import

    campaign = get_object_or_404(Campaign, pk=pk)
    try:
        campaign = set_campaign_status(
            campaign,
            request.data.get("status", ""),
            request.data.get("reason", ""),
            actor=request.user,
        )
    except RewardEngineError as exc:
        return _error(exc)
    return Response(campaign_to_dict(campaign))


@api_view(["GET"])
@permission_classes([IsAdminUser])
def posts(request):
    """Post review queue (Spec 01 §Admin UI "Posts", Spec 03 pipeline)."""
    queryset = SocialPost.objects.select_related("seller", "campaign").order_by("-published_at")
    verification_status = request.query_params.get("status")
    if verification_status:
        queryset = queryset.filter(verification_status=verification_status.upper())
    seller_code = request.query_params.get("seller_code")
    if seller_code:
        queryset = queryset.filter(seller__seller_code=seller_code)
    campaign_slug = request.query_params.get("campaign")
    if campaign_slug:
        queryset = queryset.filter(campaign__slug=campaign_slug)
    page = _page(queryset, request)
    page["results"] = [post_to_dict(p) for p in page["results"]]
    return Response(page)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def post_review(request, pk):
    """Approve or reject a tracked post (Spec 03 failure states)."""
    from apps.social.post_services import review_post  # noqa: PLC0415 - lazy import

    post = get_object_or_404(SocialPost, pk=pk)
    try:
        post = review_post(
            post,
            request.data.get("decision", ""),
            request.data.get("reason", ""),
            request.data.get("rejection_status", ""),
            actor=request.user,
        )
    except RewardEngineError as exc:
        return _error(exc)
    return Response(post_to_dict(post))


@api_view(["GET"])
@permission_classes([IsAdminUser])
def rewards(request):
    """Reward review queue (Spec 01 §Admin UI "Rewards")."""
    queryset = Reward.objects.select_related("seller", "campaign").order_by("-created_at")
    reward_status = request.query_params.get("status")
    if reward_status:
        queryset = queryset.filter(status=reward_status.upper())
    seller_code = request.query_params.get("seller_code")
    if seller_code:
        queryset = queryset.filter(seller__seller_code=seller_code)
    campaign_slug = request.query_params.get("campaign")
    if campaign_slug:
        queryset = queryset.filter(campaign__slug=campaign_slug)
    page = _page(queryset, request)
    page["results"] = [reward_to_dict(r) for r in page["results"]]
    return Response(page)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def reward_review(request, pk):
    """Approve, release, or reverse a reward (Spec 03 lifecycle; audited)."""
    from apps.rewards.services import approve_reward, make_available, reverse_reward  # noqa: PLC0415

    reward = get_object_or_404(Reward, pk=pk)
    decision = (request.data.get("decision") or "").strip().lower()
    reason = request.data.get("reason", "")
    try:
        if decision == "approve":
            reward = approve_reward(reward, actor=request.user)
        elif decision in ("available", "make_available"):
            reward = make_available(reward, actor=request.user)
        elif decision == "reverse":
            reward = reverse_reward(reward, reason, actor=request.user)
        else:
            return _error("decision must be approve, available, or reverse.")
    except RewardEngineError as exc:
        return _error(exc)
    return Response(reward_to_dict(reward))


@api_view(["GET"])
@permission_classes([IsAdminUser])
def claims(request):
    """Claim / transaction directory (Spec 01 §Admin UI "Claims"/"Transactions")."""
    queryset = Claim.objects.select_related("seller", "wallet").order_by("-created_at")
    claim_status = request.query_params.get("status")
    if claim_status:
        queryset = queryset.filter(status=claim_status.upper())
    seller_code = request.query_params.get("seller_code")
    if seller_code:
        queryset = queryset.filter(seller__seller_code=seller_code)
    transaction_hash = request.query_params.get("transaction_hash")
    if transaction_hash:
        queryset = queryset.filter(transaction_hash__iexact=transaction_hash)
    page = _page(queryset, request)
    page["results"] = [claim_to_dict(c) for c in page["results"]]
    return Response(page)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def claim_fail(request, pk):
    """Record a claim failure with a reason (the reward stays claimable)."""
    from apps.wallets.services import mark_claim_failed  # noqa: PLC0415 - lazy import

    claim = get_object_or_404(Claim, pk=pk)
    reason = (request.data.get("reason") or "").strip()
    if not reason:
        return _error("A failure reason is required.")
    try:
        claim = mark_claim_failed(claim, reason, actor=request.user)
    except RewardEngineError as exc:
        return _error(exc)
    return Response(claim_to_dict(claim))


@api_view(["GET"])
@permission_classes([IsAdminUser])
def risk_queue(request):
    """Fraud/risk review queue (Spec 01 §Admin UI "Fraud/risk", Spec 03)."""
    queryset = RiskFlag.objects.select_related("seller", "resolved_by").order_by(
        "-severity", "-created_at"
    )
    flag_status = request.query_params.get("status")
    if flag_status:
        if flag_status.upper() == "OPEN":
            queryset = risk.open_flags()
        else:
            queryset = queryset.filter(status=flag_status.upper())
    severity = request.query_params.get("severity")
    if severity:
        queryset = queryset.filter(severity=severity.upper())
    subject_type = request.query_params.get("subject_type")
    if subject_type:
        queryset = queryset.filter(subject_type=subject_type.upper())
    page = _page(queryset, request)
    page["results"] = [risk.flag_to_dict(f) for f in page["results"]]
    page["summary"] = risk.queue_summary()
    return Response(page)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def risk_resolve(request, pk):
    """Dismiss / confirm / take a risk flag into review (human decision)."""
    flag = get_object_or_404(RiskFlag, pk=pk)
    try:
        flag = risk.resolve_flag(
            flag,
            request.data.get("decision", ""),
            request.data.get("note", ""),
            actor=request.user,
        )
    except RewardEngineError as exc:
        return _error(exc)
    return Response(risk.flag_to_dict(flag))


@api_view(["POST"])
@permission_classes([IsAdminUser])
def risk_scan(request):
    """Re-run the risk scan on demand (posts + claims) — never auto-accuses."""
    hours = int(request.data.get("hours", 24))
    posts_result = risk.scan_recent_posts(hours, actor=request.user)
    claims_result = risk.evaluate_claim_volume(
        int(request.data.get("claim_threshold", 20)), actor=request.user
    )
    return Response(
        {"posts": posts_result, "claims": claims_result, "summary": risk.queue_summary()}
    )


@api_view(["GET"])
@permission_classes([IsAdminUser])
def audit_logs(request):
    """Append-only audit trail (Spec 01 §Admin UI "Audit logs")."""
    queryset = AuditLog.objects.select_related("actor").order_by("-created_at")
    action = request.query_params.get("action")
    if action:
        queryset = queryset.filter(action=action.upper())
    object_type = request.query_params.get("object_type")
    if object_type:
        queryset = queryset.filter(object_type=object_type)
    object_id = request.query_params.get("object_id")
    if object_id:
        queryset = queryset.filter(object_id=str(object_id))
    actor_username = request.query_params.get("actor")
    if actor_username:
        queryset = queryset.filter(actor__username=actor_username)
    page = _page(queryset, request)
    page["results"] = [
        {
            "id": entry.pk,
            "action": entry.action,
            "actor": entry.actor.get_username() if entry.actor_id else None,
            "object_type": entry.object_type,
            "object_id": entry.object_id,
            "metadata": entry.metadata,
            "created_at": entry.created_at.isoformat(),
        }
        for entry in page["results"]
    ]
    return Response(page)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def settings_overview(request):
    """Platform controls, token allowlist, and risk config (Spec 01 "Settings")."""
    controls = PlatformControl.objects.first()
    tokens = TokenConfig.objects.order_by("symbol")
    return Response(
        {
            "claiming_paused": bool(controls.claiming_paused) if controls else False,
            "chain": {
                "chain_id": settings.CHAIN_ID,
                "rpc_configured": bool(settings.RPC_URL),
                "contract_address": settings.CONTRACT_ADDRESS,
                "reward_token_address": settings.REWARD_TOKEN_ADDRESS,
                "signer_configured": bool(settings.CLAIM_SIGNER),
            },
            "risk": {
                "review_threshold": risk.review_threshold(),
                "signal_weights": risk.SIGNAL_WEIGHTS,
            },
            "tokens": [
                {
                    "id": token.pk,
                    "symbol": token.symbol,
                    "chain_id": token.chain_id,
                    "address": token.address,
                    "decimals": token.decimals,
                    "minimum_claim": str(token.minimum_claim),
                    "maximum_claim": str(token.maximum_claim),
                    "enabled": token.enabled,
                }
                for token in tokens
            ],
            "counts": {
                "token_configs": tokens.count(),
                "risk_flags_open": risk.open_flags().count(),
                "risk_statuses": list(RiskStatus.values),
            },
        }
    )

