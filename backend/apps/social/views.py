"""Social platform connection API (Spec 03).

Platform-agnostic: every route takes a `platform` segment so X, TikTok and any
future network share one implementation. A seller may connect several platforms
at once — they are independent accounts, not alternatives.
"""
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import SocialOAuthState, SocialPlatform
from .providers import available_platforms, get_provider, is_mock
from .providers.base import SocialProviderError
from .services import disconnect_social_account, link_social_account

logger = logging.getLogger(__name__)

# OAuth scopes per platform. Platforms differ; the mock accepts anything.
REQUIRED_SCOPES = {
    SocialPlatform.X: ["tweet.read", "users.read"],
    SocialPlatform.TIKTOK: ["user.info.basic", "video.list"],
}


def _resolve_platform(platform: str) -> str:
    """Validate the platform segment, 404 on unknown values."""
    if platform not in dict(SocialPlatform.choices):
        raise Http404(f"Unsupported platform: {platform}")
    if platform not in available_platforms():
        raise Http404(f"No adapter available for platform: {platform}")
    return platform


def _scopes_for(platform: str) -> list[str]:
    return REQUIRED_SCOPES.get(platform, [])


def _state_ttl() -> timedelta:
    """How long a connect attempt may sit between leaving for and returning from
    the provider: long enough for a login and a consent screen, short enough
    that a leaked state is worthless. Read per call so tests can override it."""
    seconds = getattr(settings, "SOCIAL_OAUTH_STATE_TTL_SECONDS", 600)
    return timedelta(seconds=seconds)


def _frontend_redirect(*, platform, connected=None, error=None):
    """Send the browser back to the app with an outcome it can display.

    The callback is a browser navigation, so it must end in a redirect rather
    than a JSON body — otherwise the seller is left staring at an API payload.
    """
    params = {"platform": platform}
    if connected:
        params["connected"] = connected
    if error:
        params["error"] = error
    return redirect(f"{settings.FRONTEND_URL}/dashboard/onboard?{urlencode(params)}")


def _no_seller():
    return Response(
        {"detail": "Create a seller profile before connecting a social account."},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def connect(request, platform):
    """Begin OAuth authorization for a platform; return its redirect URL.

    A pending `SocialOAuthState` is recorded before the URL is returned, because
    the callback comes back as a browser navigation carrying no bearer token:
    `state` is the only thing that ties it back to this user.
    """
    platform = _resolve_platform(platform)
    seller = getattr(request.user, "seller_profile", None)
    if seller is None:
        return _no_seller()

    scopes = _scopes_for(platform)
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(48)
    pending = SocialOAuthState.objects.create(
        state=state,
        platform=platform,
        user=request.user,
        code_verifier=code_verifier,
        scopes=scopes,
        expires_at=timezone.now() + _state_ttl(),
    )

    try:
        provider = get_provider(platform, user=request.user)
        authorize_url = provider.authorize(
            request, scopes, state=state, code_verifier=code_verifier
        )
    except SocialProviderError as exc:
        # No URL was produced, so the state can never be redeemed: drop it.
        pending.delete()
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response(
        {"platform": platform, "authorize_url": authorize_url, "mock": is_mock(platform)},
        status=status.HTTP_200_OK,
    )


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def callback(request, platform):
    """Complete a provider callback: resolve state, exchange code, link account.

    Public by necessity, not by choice. The provider returns the browser here as
    a top-level navigation, which carries neither the SPA's bearer token (it
    lives in `localStorage`) nor a session cookie. Trust comes from `state`
    instead: an unguessable, single-use handle recorded at connect time, which
    the network must echo back unchanged. A caller who cannot present a live
    state has no way to link anything.
    """
    platform = _resolve_platform(platform)
    state = request.query_params.get("state") or request.data.get("state")
    code = request.query_params.get("code") or request.data.get("code")

    pending = None
    if state:
        pending = (
            SocialOAuthState.objects.select_related("user")
            .filter(state=state, platform=platform)
            .first()
        )
    if pending is None or not pending.is_usable():
        return _frontend_redirect(platform=platform, error="invalid_state")

    # Single-use from here on: burn it before any network work so a replay
    # cannot reuse the handle even if the exchange below fails.
    pending.consume()

    user = pending.user
    seller = getattr(user, "seller_profile", None)
    if seller is None:
        return _frontend_redirect(platform=platform, error="no_seller")

    try:
        provider = get_provider(platform, user=user)
        identity = provider.callback(
            request, state, code, code_verifier=pending.code_verifier
        )
    except SocialProviderError as exc:
        logger.warning("OAuth callback failed for %s: %s", platform, exc)
        return _frontend_redirect(platform=platform, error=str(exc))
    except Exception:  # defensive: never strand the browser on a 500
        logger.exception("Unexpected error completing the %s OAuth callback", platform)
        return _frontend_redirect(platform=platform, error="unexpected_error")

    link_social_account(seller, identity, platform=platform, actor=user)
    return _frontend_redirect(platform=platform, connected=platform)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def disconnect(request, platform):
    """Disconnect the seller's account on one platform."""
    platform = _resolve_platform(platform)
    seller = getattr(request.user, "seller_profile", None)
    if seller is None:
        return _no_seller()

    account = seller.social_accounts.filter(platform=platform, status="CONNECTED").first()
    if not account:
        return Response(
            {"detail": f"No connected {platform} account."}, status=status.HTTP_404_NOT_FOUND
        )
    disconnect_social_account(seller, account, actor=request.user)
    return Response({"platform": platform, "detail": "Account disconnected."})


@api_view(["GET"])
@permission_classes([AllowAny])
def platforms(request):
    """Which platforms this build can connect.

    Public: it describes the build's capabilities, not the caller's data. The
    onboarding UI needs it before a user links anything, and it reveals nothing
    about who is connected — that is the authenticated `connections` endpoint.
    """
    return Response(
        {
            "platforms": [
                {"id": p, "name": dict(SocialPlatform.choices).get(p, p)}
                for p in available_platforms()
            ],
            "mock": is_mock(),
        }
    )



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def connections(request):
    """The signed-in seller's linked accounts, one entry per platform.

    Deliberately separate from `platforms/`: that endpoint says what this build
    *can* connect, this one says what *you* have connected. Without it the UI
    has to guess whether a platform is already linked before offering to
    disconnect it, and that guess surfaces as a 404 against `disconnect`.
    """
    seller = getattr(request.user, "seller_profile", None)
    if seller is None:
        return _no_seller()

    accounts = seller.social_accounts.all().order_by("-connected_at")
    return Response(
        {
            "connections": [
                {
                    "platform": a.platform,
                    "username": a.username,
                    "display_name": a.display_name,
                    "status": a.status,
                    "connected_at": a.connected_at.isoformat(),
                    "last_synced_at": a.last_synced_at.isoformat()
                    if a.last_synced_at
                    else None,
                }
                for a in accounts
            ],
            # Mirror `platforms/` so a client can tell mock from real in one call.
            "mock": is_mock(),
        }
    )
