"""Campaign API views (Spec 02)."""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.rewards.exceptions import RewardEngineError

from .models import Campaign, CampaignStatus
from .serializers import CampaignSerializer
from .services import join_campaign
from .stats import platform_stats


@api_view(["GET"])
@permission_classes([AllowAny])
def platform_stats_view(request):
    """Public headline figures for the landing page (aggregates only)."""
    return Response(platform_stats())


@api_view(["GET"])
@permission_classes([AllowAny])
def campaign_list(request):
    queryset = Campaign.objects.filter(status=CampaignStatus.ACTIVE)
    serializer = CampaignSerializer(queryset, many=True, context={"request": request})
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def campaign_detail(request, slug):
    campaign = get_object_or_404(Campaign, slug=slug)
    serializer = CampaignSerializer(campaign, context={"request": request})
    return Response(serializer.data)


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