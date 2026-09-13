"""Claims API views (Spec 02 & 04)."""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.rewards.exceptions import RewardEngineError
from apps.rewards.models import Reward

from .models import Claim, Wallet
from .services import create_claim


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def claim_create(request):
    """Create a claim authorization for an available reward.

    Body: {"reward_id": <id>, "wallet_id": <id>}
    """
    try:
        seller = request.user.seller_profile
    except Exception:
        return Response({"detail": "Seller profile required."}, status=status.HTTP_400_BAD_REQUEST)

    reward_id = request.data.get("reward_id")
    wallet_id = request.data.get("wallet_id")
    if not reward_id or not wallet_id:
        return Response(
            {"detail": "reward_id and wallet_id are required."}, status=status.HTTP_400_BAD_REQUEST
        )

    wallet = get_object_or_404(Wallet, pk=wallet_id)
    reward = get_object_or_404(Reward, pk=reward_id)

    try:
        claim = create_claim(seller, wallet, reward, actor=request.user)
    except RewardEngineError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            "id": claim.pk,
            "reward": claim.reward_id,
            "wallet": claim.wallet_id,
            "amount": str(claim.amount),
            "token_symbol": claim.token_symbol,
            "status": claim.status,
            "nonce": claim.nonce,
            "expired_at": claim.expired_at.isoformat() if claim.expired_at else None,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def claim_detail(request, pk):
    claim = get_object_or_404(Claim, pk=pk)
    if claim.seller.user_id != request.user.id and not request.user.is_staff:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(
        {
            "id": claim.pk,
            "seller_code": claim.seller.seller_code,
            "wallet": claim.wallet.address,
            "reward": claim.reward_id,
            "amount": str(claim.amount),
            "token_symbol": claim.token_symbol,
            "chain_id": claim.chain_id,
            "status": claim.status,
            "transaction_hash": claim.transaction_hash,
            "failure_reason": claim.failure_reason,
            "created_at": claim.created_at.isoformat(),
            "confirmed_at": claim.confirmed_at.isoformat() if claim.confirmed_at else None,
        }
    )