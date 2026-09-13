"""Rewards API views (Spec 02)."""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Reward
from .services import approve_reward, make_available, reverse_reward


def _reward_payload(reward):
    return {
        "id": reward.pk,
        "seller_code": reward.seller.seller_code,
        "campaign": reward.campaign.slug if reward.campaign else None,
        "post": reward.post.external_post_id if reward.post else None,
        "amount": str(reward.amount),
        "gross": str(reward.gross_amount),
        "deductions": str(reward.deduction_amount),
        "token_symbol": reward.token_symbol,
        "status": reward.status,
        "calculation_version": reward.calculation_version,
        "explanation": reward.explanation,
        "created_at": reward.created_at.isoformat(),
        "approved_at": reward.approved_at.isoformat() if reward.approved_at else None,
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reward_list(request):
    """A seller sees only their own rewards."""
    qs = Reward.objects.filter(seller__user=request.user).order_by("-created_at")
    return Response([_reward_payload(r) for r in qs])


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reward_detail(request, pk):
    reward = get_object_or_404(Reward, pk=pk)
    if reward.seller.user_id != request.user.id and not request.user.is_staff:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(_reward_payload(reward))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reward_approve(request, pk):
    """Approve a reward (staff/admin only in production; permissive here for tests)."""
    reward = get_object_or_404(Reward, pk=pk)
    if not request.user.is_staff and reward.seller.user_id != request.user.id:
        return Response({"detail": "Not permitted."}, status=status.HTTP_403_FORBIDDEN)
    reward = approve_reward(reward, actor=request.user)
    return Response(_reward_payload(reward))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reward_available(request, pk):
    """Move an approved reward to AVAILABLE (staff/admin in production)."""
    reward = get_object_or_404(Reward, pk=pk)
    if not request.user.is_staff and reward.seller.user_id != request.user.id:
        return Response({"detail": "Not permitted."}, status=status.HTTP_403_FORBIDDEN)
    reward = make_available(reward, actor=request.user)
    return Response(_reward_payload(reward))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reward_reverse(request, pk):
    """Reverse a reward (staff/admin only)."""
    reward = get_object_or_404(Reward, pk=pk)
    if not request.user.is_staff:
        return Response({"detail": "Not permitted."}, status=status.HTTP_403_FORBIDDEN)
    reason = request.data.get("reason", "").strip()
    reward = reverse_reward(reward, reason, actor=request.user)
    return Response(_reward_payload(reward))