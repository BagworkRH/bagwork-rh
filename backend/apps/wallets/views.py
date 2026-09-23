"""Wallet, claim, and authorization API views (Spec 02 & 04).

Claim flow (Spec 04):
  1. POST /api/v1/claims/                     -> create claim (server authorization)
  2. GET  /api/v1/claims/<id>/authorization/  -> signed EIP-712 payload + calldata
  3. wallet submits the transaction (frontend, using the calldata)
  4. POST /api/v1/claims/<id>/submit/         -> record the tx hash (PENDING)
  5. the chain listener confirms it           -> CONFIRMED + ledger entry
"""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.blockchain import services as chain
from apps.rewards.exceptions import RewardEngineError
from apps.rewards.models import Reward
from apps.wallets.services import (
    claim_authorization_available,
    claim_to_dict,
    create_claim,
    submit_claim,
)

from .models import Claim, Wallet


def _authorization_or_none(claim):
    """Return the signed payload, or an explanatory dict when unavailable."""
    try:
        return chain.get_claim_authorization_payload(claim), None
    except chain.BlockchainError as exc:
        return None, str(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def claim_create(request):
    """Create a claim authorization for an available reward.

    Body: {"reward_id": <id>, "wallet_id": <id>}
    Returns the claim plus, when the platform signer is configured, the signed
    authorization the frontend needs to submit the transaction.
    """
    seller = getattr(request.user, "seller_profile", None)
    if seller is None:
        return Response({"detail": "Seller profile required."}, status=status.HTTP_400_BAD_REQUEST)

    reward_id = request.data.get("reward_id")
    wallet_id = request.data.get("wallet_id")
    if not reward_id or not wallet_id:
        return Response(
            {"detail": "reward_id and wallet_id are required."}, status=status.HTTP_400_BAD_REQUEST
        )

    wallet = get_object_or_404(Wallet, pk=wallet_id, seller=seller)
    reward = get_object_or_404(Reward, pk=reward_id, seller=seller)

    try:
        claim = create_claim(seller, wallet, reward, actor=request.user)
    except RewardEngineError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    payload = claim_to_dict(claim)
    authorization, unavailable_reason = _authorization_or_none(claim)
    payload["authorization"] = authorization
    payload["authorization_ready"] = authorization is not None
    if unavailable_reason:
        payload["authorization_unavailable"] = unavailable_reason
    return Response(payload, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def claim_authorization(request, pk):
    """Return the signed EIP-712 authorization and claim transaction calldata."""
    claim = _get_claim_for_user(request, pk)

    if not claim_authorization_available(claim):
        return Response(
            {"detail": f"A claim in state {claim.status} cannot be authorized."},
            status=status.HTTP_409_CONFLICT,
        )

    authorization, unavailable_reason = _authorization_or_none(claim)
    if authorization is None:
        return Response(
            {"detail": unavailable_reason or "Authorization unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response(authorization)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def claim_submit(request, pk):
    """Record the transaction hash the seller's wallet submitted (Spec 04).

    Body: {"transaction_hash": "0x..."} (optional: the hash may also arrive
    from the chain listener).
    """
    claim = _get_claim_for_user(request, pk)
    transaction_hash = (request.data.get("transaction_hash") or "").strip()
    if not transaction_hash:
        return Response(
            {"detail": "transaction_hash is required."}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        claim = submit_claim(claim, transaction_hash=transaction_hash, actor=request.user)
    except RewardEngineError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(claim_to_dict(claim))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def claim_detail(request, pk):
    claim = _get_claim_for_user(request, pk)
    return Response(claim_to_dict(claim))


def _get_claim_for_user(request, pk) -> Claim:
    claim = get_object_or_404(Claim.objects.select_related("seller", "wallet"), pk=pk)
    if claim.seller.user_id != request.user.id and not request.user.is_staff:
        raise NotFound("Not found.")
    return claim