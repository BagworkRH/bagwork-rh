"""Social platform connection API (Spec 03).

Platform-agnostic: every route takes a `platform` segment so X, TikTok and any
future network share one implementation. A seller may connect several platforms
at once — they are independent accounts, not alternatives.
"""
from django.http import Http404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import SocialPlatform
from .providers import available_platforms, get_provider, is_mock
from .providers.base import SocialProviderError
from .services import disconnect_social_account, link_social_account

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


def _no_seller():
    return Response(
        {"detail": "Create a seller profile before connecting a social account."},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def connect(request, platform):
    """Begin OAuth authorization for a platform; return its redirect URL."""
    platform = _resolve_platform(platform)
    seller = getattr(request.user, "seller_profile", None)
    if seller is None:
        return _no_seller()

    try:
        provider = get_provider(platform, user=request.user)
        authorize_url = provider.authorize(request, _scopes_for(platform))
    except SocialProviderError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response(
        {"platform": platform, "authorize_url": authorize_url, "mock": is_mock(platform)},
        status=status.HTTP_200_OK,
    )


@api_view(["GET", "POST"])
def callback(request, platform):
    """Handle a provider callback: verify state, exchange code, link account."""
    platform = _resolve_platform(platform)
    state = request.query_params.get("state") or request.data.get("state")
    code = request.query_params.get("code") or request.data.get("code")

    if not request.user.is_authenticated:
        return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
    seller = getattr(request.user, "seller_profile", None)
    if seller is None:
        return _no_seller()

    try:
        provider = get_provider(platform, user=request.user)
        identity = provider.callback(request, state, code)
    except SocialProviderError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    account = link_social_account(seller, identity, platform=platform, actor=request.user)
    return Response(
        {
            "platform": account.platform,
            "provider_user_id": account.provider_user_id,
            "username": account.username,
            "status": account.status,
        },
        status=status.HTTP_201_CREATED,
    )


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
@permission_classes([IsAuthenticated])
def platforms(request):
    """Which platforms this build can connect."""
    return Response(
        {
            "platforms": [
                {"id": p, "name": dict(SocialPlatform.choices).get(p, p)}
                for p in available_platforms()
            ],
            "mock": is_mock(),
        }
    )