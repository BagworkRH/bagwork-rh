"""Celery tasks for blockchain operations (Spec 04 & 05).

Run continuously (or on a beat schedule):
  - process claim events (mark claims confirmed from on-chain receipts)
  - expire stale claim authorizations
  - reconcile the internal ledger with the chain
  - monitor claim volume for anomalies

Every task reports a "disabled" status when the chain is not configured, so
the scheduler can run safely before testnet deployment.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.rewards.exceptions import RewardEngineError
from apps.wallets.models import Claim, ClaimStatus
from apps.wallets.services import mark_claim_expired

from . import listener
from .reconciliation import reconcile
from .services import monitor_claim_volume

logger = logging.getLogger("apps.blockchain.tasks")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_claim_events(self, from_block=None, to_block=None):
    """Poll the distributor contract for RewardClaimed events."""
    try:
        return listener.poll_reward_claimed_events(from_block, to_block)
    except Exception as exc:  # pragma: no cover - RPC flakiness
        logger.warning("Claim event polling failed: %s", exc)
        raise self.retry(exc=exc) from exc


@shared_task
def expire_stale_claims():
    """Expire claim authorizations past their deadline.

    The reward returns to AVAILABLE so the seller can re-claim; a second
    claim is a *new* authorization (old one is already non-replayable on-chain
    via its nonce).
    """
    deadline = timezone.now() - timedelta(minutes=5)  # grace period
    stale = Claim.objects.filter(
        status__in=[ClaimStatus.CREATED, ClaimStatus.SIGNING, ClaimStatus.PENDING],
        expired_at__lt=deadline,
    )
    expired_count = 0
    for claim in stale:
        try:
            mark_claim_expired(claim)
            expired_count += 1
        except Exception:  # pragma: no cover - retried next run
            logger.exception("Could not expire claim %s", claim.pk)
            continue
    return {"expired": expired_count}


@shared_task
def reconcile_blockchain_ledger():
    """Compare internal ledger with the distributor balance."""
    return reconcile()


@shared_task
def monitor_anomalous_claims(threshold: int = 20):
    """Flag unusually high claim volume for the fraud/risk review queue."""
    return monitor_claim_volume(threshold)


@shared_task
def confirm_pending_fundings(limit: int = 50):
    """Retry verification for deposits still waiting on the chain.

    A brand's transfer is often mined before it is deep enough to credit, and
    an RPC outage can leave a verified deposit pending for a while. Both are
    resolved by asking the chain again, so this task exists to do that without
    an operator or the brand having to poll.

    Failures are counted, not raised per-deposit: one unverified hash must not
    abort the batch, and every failure leaves its deposit PENDING, which is the
    safe direction.
    """
    from apps.campaigns.funding import confirm_funding  # noqa: PLC0415 - avoids an import cycle
    from apps.campaigns.models import BrandFunding, FundingStatus  # noqa: PLC0415

    pending = BrandFunding.objects.filter(status=FundingStatus.PENDING).order_by("funded_at")[:limit]
    confirmed = 0
    still_pending = 0
    for funding in list(pending):
        try:
            confirm_funding(funding)
            confirmed += 1
        except RewardEngineError:
            # Expected while a transfer is unmined, shallow, or the RPC is down.
            still_pending += 1
        except Exception:  # pragma: no cover - unexpected, must not kill the batch
            logger.exception("Unexpected failure verifying funding %s", funding.pk)
            still_pending += 1
    return {"confirmed": confirmed, "still_pending": still_pending}