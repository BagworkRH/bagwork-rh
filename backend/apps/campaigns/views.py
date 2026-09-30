"""Campaign API views (Spec 02)."""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import (
    AllowAny,
    IsAdminUser,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
)
from rest_framework.response import Response

from apps.rewards.exceptions import RewardEngineError

from .models import Campaign, CampaignStatus
from .serializers import CampaignSerializer, CampaignWriteSerializer
from .services import create_campaign, join_campaign, set_campaign_status, update_campaign
from .stats import platform_stats


@api_view(["GET"])
@permission_classes([AllowAny])
def platform_stats_view(request):
    """Public headline figures for the landing page (aggregates only)."""
    return Response(platform_stats())


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticatedOrReadOnly])
def campaign_collection(request):
    """List active campaigns, or create one (staff only).

    A campaign is a promise about money, so creation is staff-only even though
    listing is public.
    """
    if request.method == "POST":
        return _create_campaign(request)
    queryset = Campaign.objects.filter(status=CampaignStatus.ACTIVE)
    serializer = CampaignSerializer(queryset, many=True, context={"request": request})
    return Response(serializer.data)


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticatedOrReadOnly])
def campaign_detail(request, slug):
    """Read a campaign, or edit it (staff only)."""
    campaign = get_object_or_404(Campaign, slug=slug)
    if request.method == "PATCH":
        return _update_campaign(request, campaign)
    serializer = CampaignSerializer(campaign, context={"request": request})
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def campaign_launch(request, slug):
    """Publish a draft campaign so creators can join it."""
    campaign = get_object_or_404(Campaign, slug=slug)
    try:
        campaign = set_campaign_status(campaign, CampaignStatus.ACTIVE, actor=request.user)
    except RewardEngineError as exc:
        return _error(exc)
    return Response(CampaignSerializer(campaign, context={"request": request}).data)


def _create_campaign(request):
    if not request.user.is_staff:
        return Response(
            {"detail": "Only staff can create campaigns."}, status=status.HTTP_403_FORBIDDEN
        )
    serializer = CampaignWriteSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    try:
        campaign = create_campaign(
            created_by=request.user, actor=request.user, **serializer.validated_data
        )
    except RewardEngineError as exc:
        return _error(exc)
    return Response(
        CampaignSerializer(campaign, context={"request": request}).data,
        status=status.HTTP_201_CREATED,
    )


def _update_campaign(request, campaign):
    if not request.user.is_staff:
        return Response(
            {"detail": "Only staff can edit campaigns."}, status=status.HTTP_403_FORBIDDEN
        )
    serializer = CampaignWriteSerializer(campaign, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    try:
        campaign = update_campaign(campaign, actor=request.user, **serializer.validated_data)
    except RewardEngineError as exc:
        return _error(exc)
    return Response(CampaignSerializer(campaign, context={"request": request}).data)


def _error(exc):
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def campaign_join(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    seller = getattr(request.user, "seller_profile", None)
    if seller is None:
        return Response(
            {"detail": "Create a seller profile before joining campaigns."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        participation = join_campaign(seller, campaign, actor=request.user)
    except RewardEngineError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {
            "campaign": campaign.slug,
            "seller": seller.seller_code,
            "status": participation.status,
            "joined_at": participation.joined_at.isoformat(),
        },
        status=status.HTTP_201_CREATED if participation.joined_at is not None else status.HTTP_200_OK,
    )