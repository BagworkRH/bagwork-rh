"""Celery application for asynchronous jobs (discovery, metrics, rewards)."""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("crypto_rewards")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

from config.sentry import init_sentry  # noqa: E402

# Error tracking for the worker process (no-op unless SENTRY_DSN is set).
init_sentry()