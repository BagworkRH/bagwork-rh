"""Celery tasks for the social/reward pipeline (Spec 03 synchronization).

Tasks:
  - refresh_post_metrics: pull fresh metrics and record a snapshot
  - run_verification_on_post: advance a post through the pipeline
  - calculate_pending_rewards: batch-calculate rewards for verified posts
  - flag_suspicious_activity: signal-based risk scoring stub

All provider work goes through the X provider adapter; transient errors use
exponential backoff retry.
"""
import json

from celery import shared_task
from django.utils import timezone

from apps.rewards.exceptions import RewardEngineError
from apps.social.models import (
    OriginalityEvidence,
    PostVerificationStatus,
    SocialPost,
)
from apps.social.post_services import run_verification


@shared_task(bind=True, max_retries=5, default_retry_delay=30, autoretry_for=(OSError,))
def refresh_post_metrics(self, post_id):
    """Refresh metrics for a post via the provider and record a snapshot."""
    import json  # noqa: PLC0415

    from django.utils import timezone  # noqa: PLC0415

    from .crypto_utils import decrypt_secret  # noqa: PLC0415
    from .models import PostMetricSnapshot  # noqa: PLC0415
    from .providers import get_provider  # noqa: PLC0415

    post = SocialPost.objects.get(pk=post_id)
    account = post.account
    if account is None:
        return {"status": "no-x-account", "post": post_id}

    creds = json.loads(
        decrypt_secret(bytes(account.encrypted_credentials), bytes(account.credentials_iv))
    )
    metrics = get_provider(post.platform).get_metrics(creds["access_token"], post.external_post_id)

    PostMetricSnapshot.objects.create(
        post=post,
        impressions=metrics["impressions"],
        likes=metrics["likes"],
        reposts=metrics["reposts"],
        replies=metrics["replies"],
        quotes=metrics.get("quotes", 0),
        bookmarks=metrics.get("bookmarks", 0),
        raw_provider_payload=metrics,
    )
    post.impressions = metrics["impressions"]
    post.likes = metrics["likes"]
    post.reposts = metrics["reposts"]
    post.replies = metrics["replies"]
    post.last_metrics_sync = timezone.now()
    post.save(update_fields=["impressions", "likes", "reposts", "replies", "last_metrics_sync"])
    return {"status": "ok", "post": post_id, "metrics": metrics}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def refresh_post_facts(self, post_id):
    """Re-fetch a post from its provider and overwrite the self-reported facts.

    Originality and text must come from the platform, not from whatever the
    seller typed into the submit form. Without this, a repost submitted with
    original-sounding text would verify and earn. Idempotent, and a no-op when
    the seller has no connected account to query.
    """
    from apps.social.providers import get_provider  # noqa: PLC0415
    from apps.social.providers.base import SocialProviderError  # noqa: PLC0415

    post = SocialPost.objects.get(pk=post_id)
    account = post.account
    if account is None or not account.encrypted_credentials:
        # No way to check. Do not leave the post looking self-reported-and-fine.
        post.originality_evidence = OriginalityEvidence.PROVIDER_UNAVAILABLE
        post.save(update_fields=["originality_evidence", "updated_at"])
        return {"status": "no-connected-account", "post": post_id}

    import json  # noqa: PLC0415

    from .crypto_utils import decrypt_secret  # noqa: PLC0415

    creds = json.loads(
        decrypt_secret(bytes(account.encrypted_credentials), bytes(account.credentials_iv))
    )
    provider = get_provider(post.platform, user=None)
    try:
        raw = provider.get_post(creds["access_token"], post.external_post_id)
    except SocialProviderError as exc:
        # The whole point: a provider outage must not silently pass a post
        # through as if it had been confirmed.
        post.originality_evidence = OriginalityEvidence.PROVIDER_UNAVAILABLE
        post.save(update_fields=["originality_evidence", "updated_at"])
        return {"status": "provider-error", "post": post_id, "detail": str(exc)[:200]}

    if not raw:
        # The platform no longer returns the post. Do not silently keep the
        # seller's claim; flag it for review.
        post.originality_evidence = OriginalityEvidence.PROVIDER_UNAVAILABLE
        post.set_verification(
            PostVerificationStatus.PROVIDER_ERROR,
            "Post could not be retrieved from the platform.",
        )
        return {"status": "not-found", "post": post_id}

    facts = getattr(provider, "normalize_post", None)
    payload = facts(raw) if callable(facts) else raw

    changed = ["originality_evidence"]
    if payload.get("is_repost") is not None and payload["is_repost"] != post.is_repost:
        post.is_repost = bool(payload["is_repost"])
        changed.append("is_repost")
    if payload.get("is_quote") is not None and payload["is_quote"] != post.is_quote:
        post.is_quote = bool(payload["is_quote"])
        changed.append("is_quote")
    if payload.get("text") is not None and payload["text"] != post.text_snapshot:
        post.text_snapshot = payload["text"][:5000]
        changed.append("text_snapshot")
    # Provenance records what the platform actually told us, not what we assume.
    post.originality_evidence = (
        OriginalityEvidence.PROVIDER_CONFIRMED
        if post.is_original
        else OriginalityEvidence.PROVIDER_REJECTED
    )
    post.save(update_fields=[*changed, "updated_at"])
    return {
        "status": "ok",
        "post": post_id,
        "evidence": post.originality_evidence,
        "updated": changed,
    }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_verification_on_post(self, post_id):
    """Advance a post through the verification pipeline (idempotent).

    Facts are refreshed from the platform first: a post whose originality or
    text has changed upstream must be judged on what the platform says, not on
    what was recorded at submission time. A discovered post already carries
    provider-confirmed evidence, so a refresh is not re-run over it -- that
    would overwrite a confirmed fact with a weaker one.
    """
    post = SocialPost.objects.get(pk=post_id)
    if post.verification_status == PostVerificationStatus.VERIFIED:
        return {"status": "already-verified", "post": post_id}
    already_confirmed = post.originality_evidence in (
        OriginalityEvidence.PROVIDER_CONFIRMED,
        OriginalityEvidence.PROVIDER_REJECTED,
    )
    if post.account is not None and not already_confirmed:
        refresh_post_facts(post_id)
        post.refresh_from_db()
    result = run_verification(post)
    return {"status": result.verification_status, "post": post_id}


@shared_task
def discover_posts_for_account(account_id, campaign_id):
    """Poll one connected account for new posts in one campaign, idempotently.

    Idempotency has two layers, because polling runs repeatedly by design:
    the campaign's per-platform watermark limits the window we ask the provider
    for, and `(platform, external_post_id)` uniqueness stops a second row if the
    same post still arrives.
    """
    from apps.campaigns.models import Campaign, CampaignStatus  # noqa: PLC0415
    from apps.social.models import SocialAccount  # noqa: PLC0415
    from apps.social.post_services import create_post_from_provider  # noqa: PLC0415
    from apps.social.providers import get_provider  # noqa: PLC0415
    from apps.social.providers.base import SocialProviderError  # noqa: PLC0415

    from .crypto_utils import decrypt_secret  # noqa: PLC0415

    account = SocialAccount.objects.filter(pk=account_id).first()
    campaign = Campaign.objects.filter(pk=campaign_id).first()
    if account is None or campaign is None:
        return {"status": "missing", "created": 0}
    if account.status != "CONNECTED" or campaign.status != CampaignStatus.ACTIVE:
        return {"status": "inactive", "created": 0}
    if not account.encrypted_credentials:
        return {"status": "no-credentials", "created": 0}

    creds = json.loads(
        decrypt_secret(bytes(account.encrypted_credentials), bytes(account.credentials_iv))
    )
    since = campaign.discovery_watermark(account.platform)
    now = timezone.now()

    try:
        provider = get_provider(account.platform)
        found = provider.discover_posts(
            creds["access_token"], account.provider_user_id, campaign, since, now
        )
    except SocialProviderError as exc:
        # Do NOT advance the watermark on failure: the posts we missed must be
        # re-read next tick, or a transient outage silently loses real posts.
        return {"status": "provider-error", "created": 0, "detail": str(exc)[:200]}

    created = 0
    for payload in found:
        # `from_provider` tells create_post_from_provider that originality came
        # from the platform's own record, not from anything a human typed.
        post = create_post_from_provider(
            account.seller, campaign, {**payload, "platform": account.platform, "from_provider": True}
        )
        if post is not None:
            created += 1

    campaign.set_discovery_watermark(account.platform, now)
    return {"status": "ok", "created": created, "seen": len(found)}


@shared_task
def poll_active_campaigns():
    """Fan out discovery across every active campaign and connected account.

    Bounded per account by X's per-user limit (900 requests / 15 min), so a
    moderate campaign set polls comfortably. A larger launch should shard this
    rather than raise the interval.
    """
    from apps.campaigns.models import Campaign, CampaignStatus  # noqa: PLC0415
    from apps.social.models import SocialAccount  # noqa: PLC0415

    dispatched = 0
    for campaign in Campaign.objects.filter(status=CampaignStatus.ACTIVE):
        account_ids = SocialAccount.objects.filter(
            status="CONNECTED"
        ).values_list("id", flat=True)
        for account_id in account_ids:
            discover_posts_for_account.delay(account_id, campaign.pk)
            dispatched += 1
    return {"dispatched": dispatched}


@shared_task
def calculate_pending_rewards():
    """Calculate rewards for VERIFIED posts that have no live reward."""
    from apps.rewards.services import calculate_reward  # noqa: PLC0415

    created = 0
    for post in SocialPost.objects.filter(verification_status=PostVerificationStatus.VERIFIED):
        try:
            calculate_reward(post.campaign, post, post.seller)
            created += 1
        except RewardEngineError:
            continue
    return {"created": created}


@shared_task
def flag_suspicious_activity(hours: int = 24):
    """Score recent posts and queue risk flags for human review (Spec 03).

    Delegates to `apps.audit.risk`; nothing is enforced automatically — the
    flag only describes the signals and their combined score.
    """
    from apps.audit import risk  # noqa: PLC0415

    return risk.scan_recent_posts(hours)