"""Celery tasks for the social/reward pipeline (Spec 03 synchronization).

Tasks:
  - refresh_post_metrics: pull fresh metrics and record a snapshot
  - run_verification_on_post: advance a post through the pipeline
  - calculate_pending_rewards: batch-calculate rewards for verified posts
  - flag_suspicious_activity: signal-based risk scoring stub

All provider work goes through the X provider adapter; transient errors use
exponential backoff retry.
"""
from celery import shared_task

from apps.rewards.exceptions import RewardEngineError
from apps.social.models import PostVerificationStatus, SocialPost
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
    account = post.x_account
    if account is None:
        return {"status": "no-x-account", "post": post_id}

    creds = json.loads(
        decrypt_secret(bytes(account.encrypted_credentials), bytes(account.credentials_iv))
    )
    metrics = get_provider().get_metrics(creds["access_token"], post.external_post_id)

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
def run_verification_on_post(self, post_id):
    """Advance a post through the verification pipeline (idempotent)."""
    post = SocialPost.objects.get(pk=post_id)
    if post.verification_status == PostVerificationStatus.VERIFIED:
        return {"status": "already-verified", "post": post_id}
    result = run_verification(post)
    return {"status": result.verification_status, "post": post_id}


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