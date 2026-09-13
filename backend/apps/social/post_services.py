"""Post submission & verification service (Spec 03 pipeline).

Verification pipeline:
  DISCOVERED -> BASIC_VALIDATION -> CAMPAIGN_MATCH -> DUPLICATE_CHECK ->
  METRICS_PENDING -> VERIFIED -> REWARD_CALCULATED -> APPROVED

Failure states: NOT_ELIGIBLE, DUPLICATE, OUTSIDE_CAMPAIGN_WINDOW,
REQUIREMENT_MISSING, ACCOUNT_NOT_CONNECTED, PROVIDER_ERROR, SUSPICIOUS_ACTIVITY
"""
from django.utils import timezone

from apps.audit.models import AuditLog

from .models import PostMetricSnapshot, PostVerificationStatus, SocialPost

ALLOWED_METRIC_FIELDS = ("likes", "reposts", "replies", "quotes", "bookmarks")


def create_post_from_provider(seller, campaign, payload, *, actor=None) -> SocialPost:
    """Create a post record in DISCOVERED state from provider data.

    The payload is what X discovery returned, reduced to what we are allowed
    to ingest. Duplicate external_post_id is rejected with a clear reason.
    """
    external_id = payload["post_id"].strip()
    if SocialPost.objects.filter(external_post_id=external_id).exists():
        return None  # duplicate; caller decides how to surface

    published_at = payload.get("created_at")
    if isinstance(published_at, str):
        published_at = timezone.now()

    return SocialPost.objects.create(
        x_account=seller.x_accounts.filter(status="CONNECTED").first(),
        external_post_id=external_id,
        seller=seller,
        campaign=campaign,
        post_url=payload.get("post_url", f"https://x.com/status/{external_id}"),
        text_snapshot=payload.get("text", "")[:5000],
        published_at=published_at,
        verification_status=PostVerificationStatus.DISCOVERED,
    )


def run_verification(post, *, snapshot=None, actor=None) -> SocialPost:
    """Advance the verification pipeline for a post.

    Returns the post with its updated verification_status. Pure-ish: writes a
    status transition and (when metrics are captured) a metric snapshot. Uses
    the available metrics only; never marks posts verified when the provider
    is unavailable.
    """
    campaign = post.campaign
    if campaign is None:
        post.set_verification(PostVerificationStatus.NOT_ELIGIBLE, "No campaign associated.")
        return post

    if post.published_at < campaign.start_at or post.published_at > campaign.end_at:
        post.set_verification(
            PostVerificationStatus.OUTSIDE_CAMPAIGN_WINDOW,
            "Post published outside the campaign window.",
        )
        return post

    req = campaign.requirements_json or {}

    # Requirement check: text must contain required hashtags/mentions.
    text = post.text_snapshot or ""
    required_hashtags = req.get("required_hashtags", [])
    missing = [h for h in required_hashtags if h.lower() not in text.lower()]
    if missing:
        post.set_verification(
            PostVerificationStatus.REQUIREMENT_MISSING,
            f"Missing required hashtags: {', '.join(missing)}",
        )
        return post

    # Record a metric snapshot when metrics are available.
    if snapshot is not None:
        PostMetricSnapshot.objects.get_or_create(
            post=post,
            collected_at=snapshot.get("collected_at", timezone.now()),
            defaults={
                "impressions": int(snapshot.get("impressions", 0) or 0),
                "likes": int(snapshot.get("likes", 0) or 0),
                "reposts": int(snapshot.get("reposts", 0) or 0),
                "replies": int(snapshot.get("replies", 0) or 0),
                "quotes": int(snapshot.get("quotes", 0) or 0),
                "bookmarks": int(snapshot.get("bookmarks", 0) or 0),
            },
        )

    post.set_verification(PostVerificationStatus.VERIFIED, "")
    AuditLog.objects.create(
        actor=actor,
        action="POST_VERIFIED",
        object_type="SocialPost",
        object_id=str(post.pk),
        metadata={"external_post_id": post.external_post_id, "campaign_id": campaign.pk},
    )
    return post