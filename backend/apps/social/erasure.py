"""Erasure of platform-derived content (the X data-use note, docs/10).

Two different things get called "deletion" here, and conflating them would be a
bug rather than a simplification:

* the **retention purge** runs on a schedule and strips the content from posts
  whose campaign ended long enough ago. It touches no accounts — a connected
  account is still being polled and has to keep working.
* **user-initiated deletion** erases everything belonging to one seller: their
  posts, their linked accounts and stored credentials, and their pending OAuth
  state.

Neither deletes the financial records. `Reward.post` and `Reward.seller` are
PROTECT, and rewards, claims and their amounts are what a payout dispute is
settled against — so erasure **anonymises the post in place** rather than
removing it. Deleting the row would either cascade into the ledger or fail.
"""
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.audit.models import AuditLog

from .crypto_utils import decrypt_secret
from .models import SocialOAuthState, SocialPost
from .providers import get_provider

logger = logging.getLogger(__name__)

# A reserved TLD (RFC 2606), so a tombstone can never be confused with a real
# post URL and can never resolve if something links to it.
ERASED_URL = "https://erased.invalid/"

# Bound on how much one sweep will erase, so a large backlog is spread over
# several runs instead of holding a worker for an unbounded time.
PURGE_BATCH_SIZE = 1000


def erase_post_content(post) -> bool:
    """Strip the platform-derived content from one post, in place.

    Returns whether anything changed. Idempotent: an already-erased post is left
    alone, which is what makes a re-run safe.
    """
    if post.erased_at is not None:
        return False

    post.text_snapshot = ""
    post.post_url = ERASED_URL
    # Part of a (platform, external_post_id) unique constraint, so the tombstone
    # has to stay unique — the primary key guarantees that.
    post.external_post_id = f"erased-{post.pk}"
    post.impressions = 0
    post.likes = 0
    post.reposts = 0
    post.replies = 0
    post.quotes = 0
    post.bookmarks = 0
    post.total_engagement = 0
    post.last_metrics_sync = None
    post.erased_at = timezone.now()
    post.save(
        update_fields=[
            "text_snapshot",
            "post_url",
            "external_post_id",
            "impressions",
            "likes",
            "reposts",
            "replies",
            "quotes",
            "bookmarks",
            "total_engagement",
            "last_metrics_sync",
            "erased_at",
            "updated_at",
        ]
    )
    # Snapshots exist to reproduce a reward calculation, and each carries the
    # provider's raw payload — the densest concentration of platform data we
    # hold. The reward amount is already fixed, so they can go.
    post.metric_snapshots.all().delete()
    return True


def erase_seller_posts(seller) -> int:
    """Erase the content of every post belonging to one seller."""
    erased = 0
    for post in SocialPost.objects.filter(seller=seller, erased_at__isnull=True):
        if erase_post_content(post):
            erased += 1
    return erased


def _revoke_provider_token(account) -> None:
    """Ask the platform to invalidate the token we hold, best effort.

    Erasure is deliberately not contingent on this. A provider outage must not
    leave us storing data we have promised to delete, so a failure is logged and
    the local credentials are cleared anyway.
    """
    if not account.encrypted_credentials:
        return
    try:
        creds = json.loads(
            decrypt_secret(bytes(account.encrypted_credentials), bytes(account.credentials_iv))
        )
        token = creds.get("access_token")
        if token:
            get_provider(account.platform).revoke(token)
    except Exception:  # a network failure must not block erasure
        logger.warning(
            "could not revoke the %s token during erasure", account.platform, exc_info=True
        )


def erase_seller_accounts(seller) -> int:
    """Disconnect every linked account and destroy the stored credentials."""
    erased = 0
    for account in seller.social_accounts.all():
        _revoke_provider_token(account)
        account.encrypted_credentials = b""
        account.credentials_iv = b""
        account.scopes = []
        account.token_expiry = None
        account.last_synced_at = None
        account.avatar_url = ""
        # The handle is the account's identity on the platform, so it goes too —
        # but the row stays, because posts reference it.
        account.username = f"erased-{account.pk}"
        account.display_name = ""
        account.status = "DISCONNECTED"
        account.save(
            update_fields=[
                "encrypted_credentials",
                "credentials_iv",
                "scopes",
                "token_expiry",
                "last_synced_at",
                "avatar_url",
                "username",
                "display_name",
                "status",
            ]
        )
        erased += 1
    return erased


def anonymise_user(user) -> None:
    """Replace an account's identifying fields, keeping the row.

    The row cannot be deleted: rewards reference the seller, the seller
    references the user, and `Reward.seller` is PROTECT. Deleting the user would
    either cascade into the ledger or fail outright, so the identifiers are
    replaced instead — the audit chain survives, and nothing identifies a person.
    """
    user.email = f"deleted+{user.pk}@erased.invalid"
    user.username = f"deleted-{user.pk}"
    user.first_name = ""
    user.last_name = ""
    user.is_active = False
    user.set_unusable_password()
    user.save(
        update_fields=[
            "email",
            "username",
            "first_name",
            "last_name",
            "is_active",
            "password",
            "updated_at",
        ]
    )


def erase_seller(user, *, actor=None) -> dict:
    """Erase one seller's data at their own request.

    Returns a summary, because "we deleted your data" is only credible if the
    person can be told what that amounted to.
    """
    seller = getattr(user, "seller_profile", None)
    posts = erase_seller_posts(seller) if seller else 0
    accounts = erase_seller_accounts(seller) if seller else 0
    states, _ = SocialOAuthState.objects.filter(user=user).delete()
    # DRF refuses a token whose user is inactive, so deactivating already stops
    # it working — but a credential that can never work again should not be left
    # in the table either.
    tokens, _ = Token.objects.filter(user=user).delete()

    if seller and seller.display_name:
        seller.display_name = ""
        seller.save(update_fields=["display_name", "updated_at"])

    anonymise_user(user)

    AuditLog.objects.create(
        actor=actor,
        action="SELLER_DATA_ERASED",
        object_type="User",
        object_id=str(user.pk),
        metadata={
            "posts_erased": posts,
            "accounts_erased": accounts,
            "oauth_states_deleted": states,
            "tokens_deleted": tokens,
            # Rewards and claims are deliberately untouched, and saying so in the
            # audit entry is what makes the omission a decision rather than a gap.
            "financial_records_retained": True,
        },
    )
    return {
        "status": "erased",
        "posts_erased": posts,
        "accounts_erased": accounts,
        "oauth_states_deleted": states,
        "tokens_deleted": tokens,
        "financial_records_retained": True,
    }


def purge_expired_social_data(retention_days=None, *, limit=PURGE_BATCH_SIZE) -> dict:
    """Erase content for campaigns that ended beyond the retention window.

    The window is measured from the campaign's end rather than from discovery, so
    the clock starts when the data stops being operationally useful rather than
    when it happened to be found.
    """
    days = settings.SOCIAL_RETENTION_DAYS if retention_days is None else retention_days
    cutoff = timezone.now() - timedelta(days=days)

    expired = (
        SocialPost.objects.filter(erased_at__isnull=True)
        .filter(
            # Either the campaign ended long enough ago, or the post never
            # belonged to one and is old in its own right.
            Q(campaign__end_at__lte=cutoff)
            | Q(campaign__isnull=True, discovered_at__lte=cutoff)
        )
        .order_by("pk")[:limit]
    )

    erased = sum(1 for post in expired if erase_post_content(post))
    return {
        "status": "ok",
        "erased": erased,
        "retention_days": days,
        "cutoff": cutoff.isoformat(),
    }


