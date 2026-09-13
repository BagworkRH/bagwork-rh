"""Development settings. DEBUG on, relaxed CORS, SQLite fallback for local work.

Set `DEBUG=1`, `DB_ENGINE=...` in `.env` to control behaviour. When no
PostgreSQL password is supplied the app falls back to SQLite so the project
can bootstrap without a running database.
"""
import os

from .base import *  # noqa: F401,F403
from .base import BASE_DIR  # noqa: F401

DEBUG = True
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