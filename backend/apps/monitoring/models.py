"""Monitoring models.

``Heartbeat`` is a single-row table written by a scheduled Celery task. A
supervisor or the `/api/health/` endpoint watches ``last_seen`` freshness to
detect a dead worker/beat scheduler.
"""
from django.db import models


class Heartbeat(models.Model):
    """Single-row heartbeat written every scheduling period by Celery beat."""

    id = models.BigAutoField(primary_key=True)  # always pk=1 (one row)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "heartbeat"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Heartbeat {self.last_seen.isoformat()!r}"