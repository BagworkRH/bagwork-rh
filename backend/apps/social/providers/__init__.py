"""Provider registry.

Resolves a `SocialProvider` for a given platform. Production resolves the
official adapter for each platform; the mock is gated behind `SOCIAL_PROVIDER_MODE=mock`
and is clearly marked as a development mock (Spec 05).

Keeping this registry the *only* entry point is what makes the platform layer
swappable: views, services and tasks never import a concrete adapter.
"""
import importlib

from django.conf import settings

from .base import SocialProviderError
from .metrics import instrument_provider


def provider_mode() -> str:
    """`mock` while developing, `official` in production."""
    mode = getattr(settings, "SOCIAL_PROVIDER_MODE", "")
    if mode:
        return mode
    # Backwards compatibility with the original X-only setting.
    return "mock" if getattr(settings, "X_PROVIDER", "official") == "mock" else "official"


def is_mock(platform: str | None = None) -> bool:
    return provider_mode() == "mock"


# platform -> import path of its official adapter.
REGISTRY = {
    "x": ".official:OfficialXProvider",
    "tiktok": ".tiktok:OfficialTikTokProvider",
}


def available_platforms() -> list[str]:
    """Platforms this build can serve, in display order."""
    return list(REGISTRY)


def get_provider(platform: str = "x", user=None):
    """Return the provider adapter for `platform`.

    Raises SocialProviderError for an unknown platform rather than silently
    falling back to X, so a typo cannot route a TikTok post to X.
    """
    if provider_mode() == "mock":
        from .mock import MockSocialProvider  # noqa: PLC0415

        return instrument_provider(MockSocialProvider(user, platform=platform))

    path = REGISTRY.get(platform)
    if path is None:
        raise SocialProviderError(
            f"No provider adapter registered for platform {platform!r}. "
            f"Available: {', '.join(available_platforms())}."
        )

    module_path, class_name = path.split(":")
    # Registry paths are relative to this package, so a leading-dot import is
    # not usable here; resolve against the package name explicitly.
    module = importlib.import_module(f"{__package__}{module_path}")
    return instrument_provider(getattr(module, class_name)(user))