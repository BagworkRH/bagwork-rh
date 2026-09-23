"""Blockchain status & emergency-control API (Spec 04).

- GET  /api/v1/blockchain/status/   -> chain/signer/pause status (staff)
- POST /api/v1/blockchain/control/  -> pause/unpause claiming (staff)
"""
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from . import services
from .listener import poll_reward_claimed_events


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def blockchain_status(request):
    """Chain + claim-signing + emergency state (any authenticated user)."""
    if not request.user.is_staff:
        return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
    return Response(
        {
            "chain_enabled": services.chain_enabled(),
            "signer_configured": bool(services.distributor_sign()),
            "signer_address": services.claim_signer_address(),
            "claiming_paused": services.is_claiming_paused(),
            "chain_id": settings.CHAIN_ID,
            "contract_address": settings.CONTRACT_ADDRESS,
        }
    )


@api_view(["POST"])
@permission_classes([IsAdminUser])
def control(request):
    """Emergency controls: pause/unpause claiming (admin only)."""
    action = request.data.get("action", "").strip().lower()
    if action not in ("pause_claiming", "resume_claiming"):
        return Response(
            {"detail": "action must be pause_claiming or resume_claiming."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    paused = action == "pause_claiming"
    control = services.set_claiming_paused(paused, actor=request.user)
    return Response({"claiming_paused": control.claiming_paused})


@api_view(["POST"])
@permission_classes([IsAdminUser])
def listen(request):
    """Manually trigger the event listener (admin/debug endpoint)."""
    result = poll_reward_claimed_events()
    return Response(result)