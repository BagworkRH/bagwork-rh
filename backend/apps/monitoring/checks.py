"""Production-hardening Django system checks (Spec 05 Phase 8).

Registered as *deployment* checks, so they run for
``manage.py check --deploy`` — the command deploy pipelines should gate on —
and are skipped by a plain ``manage.py check``.

Keeping them deployment-only also matters for the test suite: Django's test
runner forces ``DEBUG=False`` for the whole run, which would otherwise make a
development configuration (placeholder secret key, ``ALLOWED_HOSTS = ["*"]``)
raise errors and abort every run before a single test executes. The checks
themselves are covered by ``tests/test_monitoring.py``.

In DEBUG mode the checks are skipped as well, so local development is never
blocked; in production they fail fast on unsafe configuration.
"""
from django.conf import settings
from django.core.checks import Error, Warning, register

UNSAFE_SECRET_KEY = "unsafe-default-key-change-me"


@register(deploy=True)
def production_settings_check(app_configs, **kwargs):
    """Fail production boots on insecure settings."""
    errors = []
    if settings.DEBUG:
        return errors

    if settings.SECRET_KEY == UNSAFE_SECRET_KEY:
        errors.append(
            Error(
                "SECRET_KEY is still the insecure built-in default.",
                hint=(
                    "Set SECRET_KEY to a long random value via the environment "
                    "or a secret manager before deploying."
                ),
                id="hardening.E001",
            )
        )

    if "*" in getattr(settings, "ALLOWED_HOSTS", []):
        errors.append(
            Error(
                "ALLOWED_HOSTS must not contain '*' in production.",
                hint="List explicit hostnames (e.g. api.example.com).",
                id="hardening.E002",
            )
        )

    if not getattr(settings, "SENTRY_DSN", ""):
        errors.append(
            Warning(
                "SENTRY_DSN is not configured: error tracking is disabled.",
                hint=(
                    "Provide SENTRY_DSN (see .env.example) so exceptions are "
                    "reported to your monitoring backend."
                ),
                id="hardening.W001",
            )
        )
    return errors