"""Risk scoring and the fraud/risk review queue (Spec 03 anti-fraud).

Spec 03 signals covered here:
  - abnormal engagement spikes
  - repeated / duplicate posts
  - excessive posting frequency
  - engagement inconsistent with history
  - bot-like activity (implausible engagement ratios)
  - suspicious account patterns (one wallet reused across sellers)
  - unusual claim volume

Design rules (Spec 03: "never auto-accuse on a weak signal"):
  - scoring only *queues evidence*; it never mutates posts, rewards, or claims
  - flags below `settings.RISK_REVIEW_THRESHOLD` are not queued at all
  - a flag is advisory until a human reviewer dismisses or confirms it
"""
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone

from .models import (
    AuditLog,
    RiskFlag,
    RiskSeverity,
    RiskStatus,
    RiskSubjectType,
    severity_for_score,
)

DEFAULT_THRESHOLD = 30

# Signal weights (a score is the capped sum of the signals present). Deliberately
# conservative: no single *weak* signal reaches HIGH severity on its own, and
# several weak signals must combine before anything is queued for review.
SIGNAL_WEIGHTS = {
    "engagement_spike": 35,
    "duplicate_text": 30,
    "excessive_posting_frequency": 25,
    "engagement_inconsistent_with_history": 20,
    "bot_like_engagement_ratio": 30,
    "unusual_claim_volume": 40,
    "wallet_reused_across_sellers": 30,
}

POSTS_PER_DAY_THRESHOLD = 20
MIN_DUPLICATE_TEXT_LENGTH = 20
SPIKE_MIN_DELTA = 500
SPIKE_MIN_RATIO = 4.0
SNAPSHOT_PAIR = 2
HISTORY_MIN_IMPRESSIONS = 1000
HISTORY_MIN_ENGAGEMENT = 200
HISTORY_RATE_MULTIPLIER = 10
HISTORY_MIN_RATE = 0.05
BOT_LIKE_MIN_IMPRESSIONS = 5000
BOT_LIKE_MIN_RATE = 0.25


def review_threshold() -> int:
    """Score at or above which a signal set is queued for human review."""
    return int(getattr(settings, "RISK_REVIEW_THRESHOLD", DEFAULT_THRESHOLD))


def score_signals(signals) -> int:
    """Capped sum of the weights of the collected signals."""
    total = sum(SIGNAL_WEIGHTS.get(s["signal"], 0) for s in signals)
    return max(0, min(100, total))


def _signal(name, detail) -> dict:
    return {"signal": name, "weight": SIGNAL_WEIGHTS.get(name, 0), "detail": detail}


def collect_post_signals(post) -> list:
    """Heuristic signals for a post. Read-only: never modifies the post."""
    from apps.social.models import PostMetricSnapshot, SocialPost  # noqa: PLC0415 - lazy import

    signals = []

    snapshots = list(
        PostMetricSnapshot.objects.filter(post=post)
        .order_by("-collected_at")[:2]
        .values(
            "collected_at", "impressions", "likes", "reposts", "replies", "quotes", "bookmarks"
        )
    )
    if len(snapshots) == SNAPSHOT_PAIR:
        newer, older = snapshots  # newest first, so the delta is chronological
        metrics = ("likes", "reposts", "replies", "quotes", "bookmarks")
        older_total = sum(older[f] for f in metrics)
        newer_total = sum(newer[f] for f in metrics)
        delta = newer_total - older_total
        ratio = delta / max(older_total, 1)
        if delta >= SPIKE_MIN_DELTA and ratio >= SPIKE_MIN_RATIO:
            signals.append(
                _signal(
                    "engagement_spike",
                    {
                        "delta": delta,
                        "ratio": round(ratio, 2),
                        "from": older["collected_at"].isoformat(),
                        "to": newer["collected_at"].isoformat(),
                    },
                )
            )

    # Duplicate content: the same (long enough) text published again by the seller.
    text = (post.text_snapshot or "").strip()
    if len(text) >= MIN_DUPLICATE_TEXT_LENGTH:
        duplicate_ids = list(
            SocialPost.objects.filter(seller=post.seller, text_snapshot=text)
            .exclude(pk=post.pk)
            .values_list("external_post_id", flat=True)[:5]
        )
        if duplicate_ids:
            signals.append(
                _signal(
                    "duplicate_text",
                    {"other_posts": duplicate_ids, "count": len(duplicate_ids)},
                )
            )

    # Posting frequency: burst publishing in the 24h around this post.
    window_start = post.published_at - timedelta(hours=24)
    recent = SocialPost.objects.filter(
        seller=post.seller,
        published_at__gte=window_start,
        published_at__lte=post.published_at,
    ).count()
    if recent >= POSTS_PER_DAY_THRESHOLD:
        signals.append(_signal("excessive_posting_frequency", {"posts_in_24h": recent}))

    # Engagement inconsistent with the seller's own history.
    engagement = post.total_engagement or (
        post.likes + post.reposts + post.replies + post.quotes + post.bookmarks
    )
    impressions = post.impressions or 0
    if impressions >= HISTORY_MIN_IMPRESSIONS and engagement >= HISTORY_MIN_ENGAGEMENT:
        history = SocialPost.objects.filter(
            seller=post.seller, impressions__gte=HISTORY_MIN_IMPRESSIONS
        ).exclude(pk=post.pk)[:50]
        rates = []
        for other in history:
            other_engagement = other.total_engagement or (
                other.likes + other.reposts + other.replies + other.quotes + other.bookmarks
            )
            rates.append(other_engagement / other.impressions)
        if rates:
            average = sum(rates) / len(rates)
            current_rate = engagement / impressions
            if (
                average > 0
                and current_rate >= average * HISTORY_RATE_MULTIPLIER
                and current_rate >= HISTORY_MIN_RATE
            ):
                signals.append(
                    _signal(
                        "engagement_inconsistent_with_history",
                        {
                            "post_rate": round(current_rate, 4),
                            "seller_average_rate": round(average, 4),
                            "history_posts": len(rates),
                        },
                    )
                )

    # Bot-like activity: an implausible share of impressions engaging.
    if (
        impressions >= BOT_LIKE_MIN_IMPRESSIONS
        and engagement / max(impressions, 1) >= BOT_LIKE_MIN_RATE
    ):
        signals.append(
            _signal(
                "bot_like_engagement_ratio",
                {"impressions": impressions, "engagement": engagement},
            )
        )

    return signals


def evaluate_post(post, *, actor=None) -> RiskFlag | None:
    """Score a post and queue a review flag when the score is high enough."""
    return queue_flag(
        RiskSubjectType.POST,
        post.pk,
        seller=post.seller,
        signals=collect_post_signals(post),
        actor=actor,
    )


def scan_recent_posts(hours: int = 24, *, actor=None) -> dict:
    """Score posts published in the last `hours` (Spec 03 "flag suspicious activity")."""
    from apps.social.models import SocialPost  # noqa: PLC0415 - lazy import

    since = timezone.now() - timedelta(hours=hours)
    checked = 0
    flagged = []
    for post in SocialPost.objects.filter(published_at__gte=since):
        checked += 1
        flag = evaluate_post(post, actor=actor)
        if flag is not None:
            flagged.append(flag.pk)
    return {"checked": checked, "flagged": flagged}


def evaluate_wallet(wallet, *, actor=None) -> RiskFlag | None:
    """Flag an address that appears under more than one seller (Spec 03)."""
    from apps.wallets.models import Wallet  # noqa: PLC0415 - lazy import

    other_sellers = list(
        Wallet.objects.filter(address__iexact=wallet.address)
        .exclude(seller_id=wallet.seller_id)
        .values_list("seller__seller_code", flat=True)
        .distinct()
    )
    if not other_sellers:
        return None
    return queue_flag(
        RiskSubjectType.WALLET,
        wallet.pk,
        seller=wallet.seller,
        signals=[
            _signal(
                "wallet_reused_across_sellers",
                {"address": wallet.address, "other_sellers": other_sellers},
            )
        ],
        actor=actor,
    )


def evaluate_claim_volume(threshold_per_hour: int = 20, *, actor=None) -> dict:
    """Queue sellers exceeding the hourly claim-volume threshold (Spec 04).

    Volume alone is weak evidence, so this only ever produces a queue entry.
    """
    from apps.sellers.models import SellerProfile  # noqa: PLC0415 - lazy import
    from apps.wallets.models import Claim  # noqa: PLC0415 - lazy import

    since = timezone.now() - timedelta(hours=1)
    recent = Claim.objects.filter(created_at__gte=since)
    rows = (
        recent.values("seller_id", "seller__seller_code")
        .annotate(count=Count("id"))
        .filter(count__gte=threshold_per_hour)
        .order_by("-count")
    )

    flagged = []
    for row in rows:
        seller = SellerProfile.objects.filter(pk=row["seller_id"]).first()
        flag = queue_flag(
            RiskSubjectType.SELLER,
            row["seller_id"],
            seller=seller,
            signals=[
                _signal(
                    "unusual_claim_volume",
                    {"claims_last_hour": row["count"], "threshold": threshold_per_hour},
                )
            ],
            actor=actor,
        )
        if flag is not None:
            flagged.append(
                {
                    "seller_code": row["seller__seller_code"],
                    "count": row["count"],
                    "flag": flag.pk,
                }
            )

    checked = recent.values("seller_id").distinct().count()
    return {"checked": checked, "flagged": flagged}


def queue_flag(subject_type, subject_id, *, seller=None, signals, actor=None) -> RiskFlag | None:
    """Create or refresh the open review flag for a subject.

    Returns None when the score is below the review threshold, so weak evidence
    never enters the queue.
    """
    signals = list(signals or [])
    score = score_signals(signals)
    threshold = review_threshold()
    severity = severity_for_score(score)

    with transaction.atomic():
        existing = (
            RiskFlag.objects.select_for_update()
            .filter(
                subject_type=subject_type,
                subject_id=subject_id,
                status__in=[RiskStatus.OPEN, RiskStatus.REVIEWING],
            )
            .first()
        )

        if existing is not None:
            # Re-scoring refreshes the evidence in place (including when it
            # weakens): the queue never fills with duplicate rows.
            existing.score = score
            existing.severity = severity
            existing.signals = signals
            existing.save(update_fields=["score", "severity", "signals", "updated_at"])
            return existing

        if score < threshold:
            return None

        try:
            flag = RiskFlag.objects.create(
                subject_type=subject_type,
                subject_id=subject_id,
                seller=seller,
                score=score,
                severity=severity,
                signals=signals,
                status=RiskStatus.OPEN,
            )
        except IntegrityError:  # pragma: no cover - a concurrent scorer won the insert
            return RiskFlag.objects.filter(
                subject_type=subject_type,
                subject_id=subject_id,
                status__in=[RiskStatus.OPEN, RiskStatus.REVIEWING],
            ).first()

    AuditLog.objects.create(
        actor=actor,
        action="RISK_FLAG_QUEUED",
        object_type="RiskFlag",
        object_id=str(flag.pk),
        metadata={
            "subject_type": str(subject_type),
            "subject_id": subject_id,
            "score": score,
            "severity": severity,
            "signals": [s["signal"] for s in signals],
        },
    )
    return flag


def resolve_flag(flag, decision: str, note: str = "", *, actor=None) -> RiskFlag:
    """Dismiss, confirm, or take a flag into review (human decision; audited)."""
    from apps.rewards.exceptions import RewardEngineError  # noqa: PLC0415 - shared domain error

    mapping = {
        "dismiss": RiskStatus.DISMISSED,
        "dismissed": RiskStatus.DISMISSED,
        "confirm": RiskStatus.CONFIRMED,
        "confirmed": RiskStatus.CONFIRMED,
        "review": RiskStatus.REVIEWING,
        "reviewing": RiskStatus.REVIEWING,
    }
    decision = (decision or "").strip().lower()
    if decision not in mapping:
        raise RewardEngineError("decision must be dismiss, confirm, or review.")

    with transaction.atomic():
        locked = RiskFlag.objects.select_for_update().get(pk=flag.pk)
        locked.status = mapping[decision]
        locked.note = (note or "")[:255]
        fields = ["status", "note", "updated_at"]
        if locked.status in (RiskStatus.DISMISSED, RiskStatus.CONFIRMED):
            locked.resolved_by = actor
            locked.resolved_at = timezone.now()
            fields += ["resolved_by", "resolved_at"]
        locked.save(update_fields=fields)

    AuditLog.objects.create(
        actor=actor,
        action=f"RISK_FLAG_{locked.status}",
        object_type="RiskFlag",
        object_id=str(locked.pk),
        metadata={
            "subject_type": locked.subject_type,
            "subject_id": locked.subject_id,
            "score": locked.score,
            "note": locked.note,
        },
    )
    return locked


def open_flags():
    """The review queue: every flag still awaiting a decision."""
    return RiskFlag.objects.filter(status__in=[RiskStatus.OPEN, RiskStatus.REVIEWING])


def flag_to_dict(flag) -> dict:
    """Serialize a flag for the staff API."""
    return {
        "id": flag.pk,
        "subject_type": flag.subject_type,
        "subject_id": flag.subject_id,
        "seller_code": flag.seller.seller_code if flag.seller_id else None,
        "score": flag.score,
        "severity": flag.severity,
        "signals": flag.signals,
        "status": flag.status,
        "note": flag.note,
        "resolved_by": flag.resolved_by.get_username() if flag.resolved_by_id else None,
        "resolved_at": flag.resolved_at.isoformat() if flag.resolved_at else None,
        "created_at": flag.created_at.isoformat(),
    }


def queue_summary() -> dict:
    """Queue counts used by the admin overview."""
    pending = open_flags()
    return {
        "open": pending.count(),
        "high": pending.filter(severity=RiskSeverity.HIGH).count(),
        "medium": pending.filter(severity=RiskSeverity.MEDIUM).count(),
        "low": pending.filter(severity=RiskSeverity.LOW).count(),
        "threshold": review_threshold(),
    }
