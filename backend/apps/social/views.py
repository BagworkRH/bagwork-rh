"""X connection API views (Spec 03)."""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .providers import get_provider, is_mock
from .providers.base import XProviderError
from .services import disconnect_x_account, link_x_account

REQUIRED_SCOPES = ["tweet.read", "users.read"]


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def x_connect(request):
    """Begin OAuth authorization; return a redirect URL for the provider."""
    seller = getattr(request.user, "seller_profile", None)
    if seller is None:
        return Response(
            {"detail": "Create a seller profile before connecting X."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    provider = get_provider(request.user)
    try:
        authorize_url = provider.authorize(request, REQUIRED_SCOPES)
    except XProviderError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response(
        {"authorize_url": authorize_url, "mock": is_mock()},
        status=status.HTTP_200_OK,
    )


@api_view(["GET", "POST"])
def x_callback(request):
    """Handle the provider callback: verify state, exchange code, link account."""
    state = request.query_params.get("state") or request.data.get("state")
    code = request.query_params.get("code") or request.data.get("code")

    if not request.user.is_authenticated:
        return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        seller = request.user.seller_profile
    except Exception:
        return Response(
            {"detail": "Create a seller profile before connecting X."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    provider = get_provider(request.user)
    try:
        identity = provider.callback(request, state, code)
    except XProviderError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    account = link_x_account(seller, identity, actor=request.user)
    return Response(
        {
            "provider_user_id": account.provider_user_id,
            "username": account.username,
            "status": account.status,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def x_disconnect(request):
    """Disconnect the linked X account for the current seller."""
    try:
        seller = request.user.seller_profile
    except Exception:
        return Response({"detail": "No seller profile."}, status=status.HTTP_400_BAD_REQUEST)
    account = seller.x_accounts.filter(status="CONNECTED").first()
    if not account:
        return Response(
            {"detail": "No connected X account."}, status=status.HTTP_404_NOT_FOUND
        )
    disconnect_x_account(seller, account, actor=request.user)
    return Response({"detail": "X account disconnected."})