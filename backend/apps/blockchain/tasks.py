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