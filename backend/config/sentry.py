"""Sentry (error tracking) bootstrap — Spec 05 Phase 8 hardening.

A strict no-op unless ``SENTRY_DSN`` is configured, so local development and
the test suite never require Sentry. Called from the WSGI/ASGI entrypoints
and the Celery worker so every process reports to the same project.
"""


def init_sentry():
    """Initialise the Sentry SDK for the current process (idempotent, safe)."""
    try:
        # Imported lazily: `django.conf.settings` is only readable after the
        # Django setup call in the entrypoint, and the SDK is an optional dep.
        from django.conf import settings  # noqa: PLC0415

        dsn = getattr(settings, "SENTRY_DSN", "")
        if not dsn:
            return
        import sentry_sdk  # noqa: PLC0415  (guarded: only when actually needed)

        sentry_sdk.init(
            dsn=dsn,
            environment=getattr(settings, "ENVIRONMENT", ""),
            traces_sample_rate=getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.0),
            send_default_pii=False,  # never attach user PII to events
        )
    except (ImportError, Exception):  # pragma: no cover - never break boot
        # Sentry is best-effort: a missing SDK or bad DSN must not crash the app.
        return