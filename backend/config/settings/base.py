"""
Base Django settings for bagworkRH.

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
    "apps.monitoring",
]

MIDDLEWARE = [
    # Outermost: assigns/binds the request id before anything else runs, so
    # every log line for a request is correlatable (Spec 05 Phase 8).
    "config.observability.RequestIDMiddleware",
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
        "NAME": os.environ.get("DB_NAME", "bagwork_rh"),
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
    # Production hardening (Spec 05 Phase 8): global rate limiting.
    # The scoped classes are path-selective (see `config/throttling.py`) and
    # only throttle auth / admin / wallet surfaces; the baselines cover
    # everything else. All rates are tunable via THROTTLE_* env vars.
    "DEFAULT_THROTTLE_CLASSES": [
        "config.throttling.AdminThrottle",
        "config.throttling.AuthThrottle",
        "config.throttling.WalletThrottle",
        "config.throttling.SubmissionThrottle",
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.environ.get("THROTTLE_ANON", "100/hour"),
        "user": os.environ.get("THROTTLE_USER", "1000/hour"),
        "auth": os.environ.get("THROTTLE_AUTH", "10/hour"),
        "admin": os.environ.get("THROTTLE_ADMIN", "120/hour"),
        "wallet": os.environ.get("THROTTLE_WALLET", "30/hour"),
        # Post submission leads to a payout, so its ceiling sits far below the
        # general `user` rate: 1000/hour is a scraping guard, not an anti-abuse
        # control. A creator submitting by hand never approaches this.
        "submit": os.environ.get("THROTTLE_SUBMIT", "20/hour"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

# Error tracking (Spec 05 Phase 8). Strict no-op unless SENTRY_DSN is set;
# `config/sentry.py` bootstraps the SDK from these values.
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0"))
ENVIRONMENT = os.environ.get("ENVIRONMENT", "")
HEARTBEAT_STALE_SECONDS = int(os.environ.get("HEARTBEAT_STALE_SECONDS", "300"))

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
    # Social discovery (Stage 3). Polls each connected account per active
    # campaign. 5 minutes keeps a creator's reward within minutes of posting
    # while staying well inside X's 900 req/15min per-user limit and TikTok's
    # video.list page cap. Tied to the per-campaign watermark, so a tick that
    # finds nothing new costs one request.
    "poll-social-discovery": {
        "task": "apps.social.tasks.poll_active_campaigns",
        "schedule": timedelta(minutes=5),
    },
    "poll-reward-claimed-events": {
        "task": "apps.blockchain.tasks.process_claim_events",
        "schedule": 120.0,  # every 2 minutes
    },
    "expire-stale-claims": {
        "task": "apps.blockchain.tasks.expire_stale_claims",
        "schedule": timedelta(minutes=15),
    },
    # Re-verify brand deposits that are still waiting. A transfer usually needs
    # a few blocks before it is final, and an RPC blip can strand a deposit that
    # was actually paid for, so the retry lives here rather than depending on a
    # brand noticing and asking again.
    "confirm-pending-fundings": {
        "task": "apps.blockchain.tasks.confirm_pending_fundings",
        "schedule": timedelta(minutes=2),
    },
    "monitor-anomalous-claims": {
        "task": "apps.blockchain.tasks.monitor_anomalous_claims",
        "schedule": timedelta(hours=1),
    },
    "reconcile-blockchain-ledger": {
        "task": "apps.blockchain.tasks.reconcile_blockchain_ledger",
        "schedule": timedelta(hours=6),
    },
    "scan-risk-signals": {
        "task": "apps.social.tasks.flag_suspicious_activity",
        "schedule": timedelta(hours=1),
    },
    # Phase 8: worker/beat liveness heartbeat written every minute.
    "monitoring-heartbeat": {
        "task": "apps.monitoring.tasks.heartbeat",
        "schedule": 60.0,
    },
}

# Frontend URL used for building callback links etc.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

# Social platform providers (Spec 03).
# SOCIAL_PROVIDER_MODE is "official" (each platform's real API) or "mock" (the
# clearly-marked development mock, used for every platform). Credentials are
# per-platform and read from the environment; none are ever hard-coded.
SOCIAL_PROVIDER_MODE = os.environ.get("SOCIAL_PROVIDER_MODE", "official")

# X (Twitter) — https://developer.x.com
X_CLIENT_ID = os.environ.get("X_CLIENT_ID", "")
X_CLIENT_SECRET = os.environ.get("X_CLIENT_SECRET", "")
X_REDIRECT_URI = os.environ.get("X_REDIRECT_URI", "")

# TikTok — https://developers.tiktok.com
TIKTOK_CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
TIKTOK_REDIRECT_URI = os.environ.get("TIKTOK_REDIRECT_URI", "")

# Blockchain (Spec 04)
# RPC_URL / CONTRACT_ADDRESS empty => the chain services run disabled and
# claim/listener/reconciliation tasks report "disabled" instead of failing.
# Default chain is Robinhood Chain testnet (Arbitrum L2), the launch chain:
#   testnet: CHAIN_ID=46630  https://rpc.testnet.chain.robinhood.com
#   mainnet: CHAIN_ID=4663   https://rpc.mainnet.chain.robinhood.com
CHAIN_ID = int(os.environ.get("CHAIN_ID", "46630"))          # Robinhood Chain testnet
RPC_URL = os.environ.get("RPC_URL", "")
CONTRACT_ADDRESS = os.environ.get("CONTRACT_ADDRESS", "")       # RewardDistributor
REWARD_TOKEN_ADDRESS = os.environ.get("REWARD_TOKEN_ADDRESS", "")
# EIP-712 domain name. MUST match RewardDistributor.sol exactly: it is hashed
# into the on-chain DOMAIN_SEPARATOR, and a mismatch means every signature the
# backend produces is rejected by the contract. Deploy-time guard lives in
# contracts/src/reward_token/scripts/deploy.ts.
EIP712_DOMAIN_NAME = os.environ.get("EIP712_DOMAIN_NAME", "bagworkRH")
# Claim-authorization signer (private key, testnet dev key). NEVER commit a
# production key. Signer address is derived from the key at runtime.
CLAIM_SIGNER = os.environ.get("CLAIM_SIGNER", "")
CLAIM_SIGNER_ADDRESS = os.environ.get("CLAIM_SIGNER_ADDRESS", "")
DEFAULT_TOKEN_DECIMALS = int(os.environ.get("TOKEN_DECIMALS", "18"))
# The stablecoin brands fund with and creators are paid in. One symbol, one
# source of truth: it was previously written as a literal in the funding model,
# the quote endpoint and the frontend, which is how a token rename becomes a
# multi-file sweep that quietly misses a spot.
#
# USDG is Paxos's Global Dollar, a dollar-denominated stablecoin, chosen
# because it is the stablecoin Robinhood Chain actually documents (alongside
# WETH). No USDC contract is published for this chain, so a USDC rail could not
# have been enabled as written. The substance is unchanged: a dollar stablecoin
# means a creator's payout holds its value and the platform never converts to
# fiat, so it is not acting as an exchanger.
#
# USDG is 6 decimals on both Robinhood Chain networks (read from the chain, not
# assumed). Decimals are never taken from this setting — they come from the
# TokenConfig allowlist at runtime, because quoting a 15% fee at the wrong
# precision produces a number the chain will not honour.
#
# Must be allowlisted for the campaign's chain, or campaigns paying in it are
# refused at creation (see campaigns.services._validate_token_allowed).
FUNDING_TOKEN_SYMBOL = os.environ.get("FUNDING_TOKEN_SYMBOL", "USDG")
# The address brands must actually send funding to. A deposit is only credited
# when the receipt shows the allowlisted token transferring to THIS address, so
# it is a hard gate rather than a display value: left empty, no deposit can be
# confirmed at all. That is intentional. Before this check existed, a brand
# could point at a real transfer of its own stablecoin to a wallet it controls
# and have the platform credit it as funding.
FUNDING_TREASURY_ADDRESS = os.environ.get("FUNDING_TREASURY_ADDRESS", "")
# Confirmations a deposit needs before it counts as final. A transaction with
# zero confirmations can still be reorged out, so crediting immediately credits
# a promise. 3 is the usual floor for "this is not going away".
FUNDING_CONFIRMATIONS = int(os.environ.get("FUNDING_CONFIRMATIONS", "3"))
# Platform fee in basis points, charged on top of the creator payout and never
# deducted from it (must match RewardDistributor.PLATFORM_FEE_BPS = 1500).
# 1500 = 15%: a $5 payout costs a brand $5.75, the creator still receives $5.
PLATFORM_FEE_BPS = int(os.environ.get("PLATFORM_FEE_BPS", "1500"))

# Fraud/risk review queue (Spec 03 anti-fraud). Signals scoring at or above this
# threshold are queued for human review; nothing is ever actioned automatically.
RISK_REVIEW_THRESHOLD = int(os.environ.get("RISK_REVIEW_THRESHOLD", "30"))

# Structured logging (Spec 05 Phase 8). `LOG_FORMAT=json` emits one JSON object
# per line for a log pipeline; the default text formatter stays readable in
# development. Every line carries the request id bound by RequestIDMiddleware.
LOG_FORMAT = os.environ.get("LOG_FORMAT", "text").strip().lower()

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "config.observability.RequestIDFilter"},
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} [req:{request_id}] {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} [req:{request_id}] {message}",
            "style": "{",
        },
        "json": {"()": "config.observability.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if LOG_FORMAT == "json" else "simple",
            "filters": ["request_id"],
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