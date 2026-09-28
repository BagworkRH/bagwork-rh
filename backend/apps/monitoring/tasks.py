"""Celery heartbeat task (Spec 05 Phase 8 monitoring)."""
import logging

from celery import shared_task

from .models import Heartbeat

logger = logging.getLogger("apps.monitoring")


@shared_task(name="apps.monitoring.tasks.heartbeat", ignore_result=True)
def heartbeat():
    """Write a fresh `last_seen` timestamp into the single heartbeat row."""
    row = Heartbeat.objects.first()
    if row is None:
        row = Heartbeat(pk=1)
    row.save()
    logger.info("heartbeat written: %s", row.last_seen.isoformat())
    return {"heartbeat": row.last_seen.isoformat()}