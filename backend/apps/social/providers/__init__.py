"""Provider registry.

Production code uses the official X API adapter; the mock is gated behind
`X_PROVIDER=mock` and is clearly marked as a development mock (Spec 05).
"""
from django.conf import settings


def get_provider(user=None):
    """Return the active X provider instance for the current environment."""
    provider_name = getattr(settings, "X_PROVIDER", "official")

    if provider_name == "mock":
        from .mock import MockXProvider  # noqa: PLC0415

        return MockXProvider(user)

    from .official import OfficialXProvider  # noqa: PLC0415

    return OfficialXProvider(user)


def is_mock() -> bool:
    return getattr(settings, "X_PROVIDER", "official") == "mock"