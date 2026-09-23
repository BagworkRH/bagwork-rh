"""
Base Django settings for the Crypto Social Rewards Platform.

Settings here are shared across environments. Environment-specific values are
sourced from environment variables (see `.env.example`). Secrets must never be
committed; always go through environment variables or a secret manager.
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / "subdir".
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load environment variables from a local `.env` file when present.
load_dotenv(BASE_DIR / ".env")


def _bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list(name, default=None):
    value = os.environ.get(name)
    if not value:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = os.environ.get("SECRET_KEY", "unsafe-default-key-change-me")
DEBUG = _bool("DEBUG", False)
ALLOWED_HOSTS = _list("ALLOWED_HOSTS", ["*"])
CSRF_TRUSTED_ORIGINS = _list("CSRF_TRUSTED_ORIGINS")
CORS_ALLOWED_ORIGINS = _list("CORS_ALLOWED_ORIGINS")

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    # Local apps
    "apps.accounts",
    "apps.sellers",
    "apps.campaigns",
    "apps.social",
    "apps.rewards",
    "apps.wallets",
    "apps.blockchain",
    "apps.audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database. Defaults to PostgreSQL; dev settings fall back to SQLite locally.
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": os.environ.get("DB_NAME", "crypto_rewards"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Authentication: use a custom user model from the start.
AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Celery / Redis
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"

# Periodic blockchain jobs (Spec 04/05). Each task reports a "disabled" status
# when RPC_URL/CONTRACT_ADDRESS are unset, so the scheduler is safe to run
# before testnet deployment.
CELERY_BEAT_SCHEDULE = {
    "poll-reward-claimed-events": {
        "task": "apps.blockchain.tasks.process_claim_events",
        "schedule": 120.0,  # every 2 minutes
    },
    "expire-stale-claims": {
        "task": "apps.blockchain.tasks.expire_stale_claims",
        "schedule": timedelta(minutes=15),
    },
    "monitor-anomalous-claims": {
        "task": "apps.blockchain.tasks.monitor_anomalous_claims",
        "schedule": timedelta(hours=1),
    },
    "reconcile-blockchain-ledger": {
        "task": "apps.blockchain.tasks.reconcile_blockchain_ledger",
        "schedule": timedelta(hours=6),
    },
}

# Frontend URL used for building callback links etc.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

# X provider: "official" (X API) or "mock" (development mock only).
X_PROVIDER = os.environ.get("X_PROVIDER", "official")
X_CLIENT_ID = os.environ.get("X_CLIENT_ID", "")
X_CLIENT_SECRET = os.environ.get("X_CLIENT_SECRET", "")
X_REDIRECT_URI = os.environ.get("X_REDIRECT_URI", "")

# Blockchain (Spec 04)
# RPC_URL / CONTRACT_ADDRESS empty => the chain services run disabled and
# claim/listener/reconciliation tasks report "disabled" instead of failing.
CHAIN_ID = int(os.environ.get("CHAIN_ID", "11155111"))          # Sepolia testnet
RPC_URL = os.environ.get("RPC_URL", "")
CONTRACT_ADDRESS = os.environ.get("CONTRACT_ADDRESS", "")       # RewardDistributor
REWARD_TOKEN_ADDRESS = os.environ.get("REWARD_TOKEN_ADDRESS", "")
# Claim-authorization signer (private key, testnet dev key). NEVER commit a
# production key. Signer address is derived from the key at runtime.
CLAIM_SIGNER = os.environ.get("CLAIM_SIGNER", "")
CLAIM_SIGNER_ADDRESS = os.environ.get("CLAIM_SIGNER_ADDRESS", "")
DEFAULT_TOKEN_DECIMALS = int(os.environ.get("TOKEN_DECIMALS", "18"))

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}