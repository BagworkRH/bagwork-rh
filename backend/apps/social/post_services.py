"""Post submission & verification service (Spec 03 pipeline).

Verification pipeline:
  DISCOVERED -> BASIC_VALIDATION -> CAMPAIGN_MATCH -> DUPLICATE_CHECK ->
  METRICS_PENDING -> VERIFIED -> REWARD_CALCULATED -> APPROVED

Failure states: NOT_ELIGIBLE, DUPLICATE, OUTSIDE_CAMPAIGN_WINDOW,
REQUIREMENT_MISSING, ACCOUNT_NOT_CONNECTED, PROVIDER_ERROR, SUSPICIOUS_ACTIVITY
"""
from django.utils import timezone

from apps.audit.models import AuditLog

from .models import (
    OriginalityEvidence,
    PostMetricSnapshot,
    PostVerificationStatus,
    SocialPlatform,
    SocialPost,
)

ALLOWED_METRIC_FIELDS = ("likes", "reposts", "replies", "quotes", "bookmarks")

# Failure states a reviewer may apply when rejecting a post (Spec 03).
REVIEW_REJECTION_STATUSES = (
    PostVerificationStatus.NOT_ELIGIBLE,
    PostVerificationStatus.DUPLICATE,
    PostVerificationStatus.OUTSIDE_CAMPAIGN_WINDOW,
    PostVerificationStatus.REQUIREMENT_MISSING,
    PostVerificationStatus.PROVIDER_ERROR,
    PostVerificationStatus.SUSPICIOUS_ACTIVITY,
)


def create_post_from_provider(seller, campaign, payload, *, actor=None) -> SocialPost:
    """Create a post record in DISCOVERED state from provider data.

    The payload is what the platform provider returned, reduced to what we are
    allowed to ingest. `platform` is part of a post's identity: the same
    external_post_id on two platforms is two different posts.
    """
    platform = payload.get("platform", SocialPlatform.X)
    external_id = payload["post_id"].strip()
    if SocialPost.objects.filter(platform=platform, external_post_id=external_id).exists():
        return None  # duplicate; caller decides how to surface

    published_at = payload.get("created_at")
    if isinstance(published_at, str):
        published_at = timezone.now()

    return SocialPost.objects.create(
        account=seller.social_accounts.filter(
            platform=platform, status="CONNECTED"
        ).first(),
        platform=platform,
        external_post_id=external_id,
        seller=seller,
        campaign=campaign,
        is_repost=bool(payload.get("is_repost", False)),
        is_quote=bool(payload.get("is_quote", False)),
        post_url=payload.get("post_url", f"https://x.com/status/{external_id}"),
        text_snapshot=payload.get("text", "")[:5000],
        published_at=published_at,
        verification_status=PostVerificationStatus.DISCOVERED,
    )


def _originality_failure(post, req):
    """Return (status, reason) if the post cannot earn on originality grounds.

    Two independent gates, deliberately separate:

    * The *flag* gate looks at is_repost/is_quote. Waivable via
      `allow_non_original` for research campaigns.
    * The *evidence* gate asks whether the platform actually confirmed this.
      Paying out on an assumption is how a rewards program gets farmed, so
      when the provider was unreachable we do not fall back to trusting the
      seller -- the post waits for a human. A provider that positively said
      "repost" is never overridden by `allow_non_original`.
    """
    if not post.is_original and not req.get("allow_non_original", False):
        kind = "repost" if post.is_repost else "quote"
        return (
            PostVerificationStatus.NOT_ORIGINAL,
            f"Post is a {kind}, not original content; not eligible for a reward.",
        )

    if req.get("allow_unconfirmed_originality", False):
        return None

    if post.originality_evidence == OriginalityEvidence.PROVIDER_REJECTED:
        return (
            PostVerificationStatus.NOT_ORIGINAL,
            "The platform reports this post is not original.",
        )
    if post.originality_evidence != OriginalityEvidence.PROVIDER_CONFIRMED:
        return (
            PostVerificationStatus.PROVIDER_ERROR,
            "Originality not confirmed by the platform; needs review before "
            "this post can earn. No reward is paid on an unverified claim.",
        )
    return None


def _disclosure_failure(post, req):
    """Return (status, reason) if a required disclosure is missing."""
    text = post.text_snapshot or ""
    missing = [d for d in req.get("required_disclosure", []) if d.lower() not in text.lower()]
    if not missing:
        return None
    return (
        PostVerificationStatus.NOT_DISCLOSED,
        f"Missing required disclosure: {', '.join(missing)}",
    )


def _hashtag_failure(post, req):
    """Return (status, reason) if a required hashtag is missing."""
    text = post.text_snapshot or ""
    missing = [h for h in req.get("required_hashtags", []) if h.lower() not in text.lower()]
    if not missing:
        return None
    return (
        PostVerificationStatus.REQUIREMENT_MISSING,
        f"Missing required hashtags: {', '.join(missing)}",
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

    # Order matters: originality before disclosure, both before hashtags, so
    # the most fundamental reason is the one a creator sees first.
    for check in (_originality_failure, _disclosure_failure, _hashtag_failure):
        failure = check(post, req)
        if failure is not None:
            post.set_verification(*failure)
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


def review_post(post, decision, reason="", rejection_status="", *, actor=None) -> SocialPost:
    """Human review of a tracked post from the admin back-office (Spec 05 Phase 7).

    Records at most a verification status + reason; it never pays out or deletes
    anything. Approving marks the post VERIFIED (rewards are still calculated
    separately by the reward engine), rejecting applies a Spec 03 failure state.
    """
    from apps.rewards.exceptions import RewardEngineError  # noqa: PLC0415 - shared domain error

    decision = (decision or "").strip().lower()
    if decision in ("approve", "approved", "verify", "verified"):
        previous = post.verification_status
        post.set_verification(PostVerificationStatus.VERIFIED, "")
        AuditLog.objects.create(
            actor=actor,
            action="POST_REVIEW_APPROVED",
            object_type="SocialPost",
            object_id=str(post.pk),
            metadata={
                "external_post_id": post.external_post_id,
                "seller_code": post.seller.seller_code,
                "from": previous,
                "to": PostVerificationStatus.VERIFIED,
            },
        )
        return post

    if decision in ("reject", "rejected"):
        status_value = rejection_status or PostVerificationStatus.NOT_ELIGIBLE
        if status_value not in REVIEW_REJECTION_STATUSES:
            raise RewardEngineError(
                "rejection_status must be one of: " + ", ".join(REVIEW_REJECTION_STATUSES) + "."
            )
        if not reason:
            raise RewardEngineError("A rejection reason is required.")
        post.set_verification(status_value, reason[:255])
        AuditLog.objects.create(
            actor=actor,
            action="POST_REVIEW_REJECTED",
            object_type="SocialPost",
            object_id=str(post.pk),
            metadata={
                "external_post_id": post.external_post_id,
                "seller_code": post.seller.seller_code,
                "status": status_value,
                "reason": reason,
            },
        )
        return post

    raise RewardEngineError("decision must be approve or reject.")