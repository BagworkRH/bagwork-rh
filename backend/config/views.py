"""Health check endpoint used by load balancers / CI."""

import redis
from django.conf import settings
from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


def _database_ok():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True
    except Exception:  # pragma: no cover - depends on infra state
        return False


def _redis_ok():
    """Best-effort Redis ping; Redis is optional in local dev."""
    if not settings.REDIS_URL:
        return "unconfigured"
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        client.ping()
        return "ok"
    except Exception:  # pragma: no cover - depends on infra state
        return "error"


def _heartbeat_status():
    """Freshness of the Celery beat `Heartbeat` row (Phase 8 monitoring)."""
    try:
        # Lazily imported so the health probe stays functional even before
        # the monitoring app is migrated (returns "unset").
        from apps.monitoring.models import Heartbeat  # noqa: PLC0415

        row = Heartbeat.objects.first()
    except Exception:  # pragma: no cover - model may not be migrated yet
        return "unset"
    if row is None:
        return "unset"
    age_seconds = (timezone.now() - row.last_seen).total_seconds()
    if age_seconds <= settings.HEARTBEAT_STALE_SECONDS:
        return "ok"
    return "stale"


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Report application liveness and dependency connectivity."""
    db_ok = _database_ok()
    redis_state = _redis_ok()
    heartbeat_state = _heartbeat_status()

    overall = "ok" if db_ok else "degraded"
    http_code = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(
        {
            "status": overall,
            "database": "ok" if db_ok else "error",
            "redis": redis_state,
            "heartbeat": heartbeat_state,
            "service": "crypto-social-rewards",
            "checks": {
                "database": "ok" if db_ok else "error",
                "redis": redis_state,
                "heartbeat": heartbeat_state,
            },
        },
        status=http_code,
    )