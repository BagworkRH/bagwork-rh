"""Provider call instrumentation (Spec 05 Phase 8).

Every provider API call is timed and logged with a structured outcome
(``provider``, ``operation``, ``outcome``, ``latency_ms``), so a log pipeline can
chart failure rate and latency per platform and an alert can fire on a provider
outage — the signal Phase 8's "a provider outage pages someone" needs.

Instrumentation is applied to the *instance* in `get_provider`, not the class,
for two reasons: ``isinstance(provider, OfficialXProvider)`` must keep holding,
and wrapping one adapter must not leak onto another (or onto the class shared by
every caller).
"""
import logging
import time
from functools import wraps

logger = logging.getLogger("apps.social.providers")

# Methods that hit the platform API. `authorize` is omitted: it only builds a
# local URL and makes no network call, so timing it measures nothing.
METERED_METHODS = (
    "callback",
    "get_account",
    "discover_posts",
    "get_post",
    "get_metrics",
    "revoke",
)


def _instrument(platform, operation, func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        started = time.perf_counter()
        outcome = "ok"
        try:
            return func(*args, **kwargs)
        except Exception:
            outcome = "error"
            raise
        finally:
            logger.info(
                "provider call",
                extra={
                    "structured": {
                        "provider": platform,
                        "operation": operation,
                        "outcome": outcome,
                        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                },
            )

    return wrapper


def instrument_provider(provider):
    """Wrap a provider instance's API methods to emit a metric line per call."""
    platform = getattr(provider, "platform", "") or ""
    for name in METERED_METHODS:
        func = getattr(provider, name, None)
        if callable(func):
            setattr(provider, name, _instrument(platform, name, func))
    return provider
