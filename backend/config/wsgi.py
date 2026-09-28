"""WSGI config for the Crypto Social Rewards Platform."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

from config.sentry import init_sentry  # noqa: E402

application = get_wsgi_application()

# Error tracking (no-op unless SENTRY_DSN is configured).
init_sentry()