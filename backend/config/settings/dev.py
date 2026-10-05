"""Development settings. DEBUG on, relaxed CORS, SQLite fallback for local work.

`DEBUG` and `DB_ENGINE` are read from the environment so the DEBUG=False guard
in dev-only management commands (e.g. `seed_demo`) actually works. When no
PostgreSQL password is supplied the app falls back to SQLite so the project
can bootstrap without a running database.
"""
import os

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, REST_FRAMEWORK, _bool  # noqa: F401

# Defaults to on locally; set DEBUG=0 in the environment to disable.
DEBUG = _bool("DEBUG", True)
ALLOWED_HOSTS = ["*"]

# Local CORS: allow the Next.js dev server.
CORS_ALLOW_ALL_ORIGINS = True

# Use SQLite locally when no PostgreSQL credentials are supplied.
if os.environ.get("DB_PASSWORD"):
    # Keep PostgreSQL config from base.
    pass
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Development tolerance for rate limits: a generous per-hour budget so local
# work and the test-suite never trip 429s. Production uses the strict
# env-driven rates from base.py (THROTTLE_*). Individual scopes can still be
# tightened via env vars if you want to exercise throttling locally.
# A new dict is built (rather than mutating the imported one) so `base` keeps
# its own untouched copy of the production rates.
#
# Scope names are *derived* from base rather than listed here. Hand-listing
# meant every new throttle scope had to be added in two places, and forgetting
# the second produced a 500 on every request in the whole suite — because
# `PathScopedThrottle.get_rate` correctly raises for a scope with no rate —
# instead of one clear failure at the point of the mistake.
_BASE_RATES = REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        scope: os.environ.get(f"THROTTLE_{scope.upper()}", "100000/hour")
        for scope in _BASE_RATES
    },
}