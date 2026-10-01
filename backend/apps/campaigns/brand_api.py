"""Brand-facing API: onboarding, stablecoin funding, and campaign cost quotes.

A brand is a paying customer, so these endpoints answer the three questions a
brand actually has: how do I pay, what does my campaign cost, and what have I
funded so far. Every view is scoped to the signed-in user's own brand; there
is no path here by which one brand can read or fund another's account.
"""
from decimal import Decimal

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.blockchain import fees
from apps.rewards.exceptions import RewardEngineError

from .funding import (
    confirm_funding,
    confirmed_funded_balance,
    get_or_create_brand,
    quote_campaign_cost,
    record_funding,
)
from .models import (
    BrandFunding,
    Campaign,
)
from .serializers import BrandFundingSerializer, BrandProfileSerializer


def _brand_for(user, *, create_from=None):
    """The caller's brand, or None. Never another brand's."""
    brand = getattr(user, "brand_profile", None)
    if brand is not None or create_from is None:
        return brand
    return get_or_create_brand(user, company_name=create_from, actor=user)


def _error(exc):
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def funding_token_symbol() -> str:
    """The stablecoin brands fund with and creators are paid in.

    Read from settings rather than hardcoded so the symbol has one definition.
    See `FUNDING_TOKEN_SYMBOL` for why this is USDG and not USDC.
    """
    return str(getattr(settings, "FUNDING_TOKEN_SYMBOL", "USDG"))


def funding_token_decimals() -> int:
    """Precision of the funding token, from the allowlist.

    Read rather than assumed: the platform default is 18, and quoting a fee at
    the wrong precision produces a number the chain would never charge. Falls
    back to the default only when the token is not yet registered.
    """
    from apps.blockchain.models import TokenConfig  # noqa: PLC0415 - lazy: avoids a cycle

    token = TokenConfig.objects.filter(symbol__iexact=funding_token_symbol()).first()
    return token.decimals if token else fees.DEFAULT_DECIMALS


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def brand_profile(request):
    """Read or create the caller's brand profile.

    POST is idempotent: a user who already has a brand gets that brand back
    rather than a duplicate, so a double-clicked signup cannot create two.
    """
    if request.method == "POST":
        company_name = (request.data.get("company_name") or "").strip()
        if not company_name:
            return Response(
                {"company_name": ["A company name is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        brand = _brand_for(
            request.user,
            create_from=company_name,
        )
        if request.data.get("contact_email"):
            brand.contact_email = request.data["contact_email"].strip()
            brand.save(update_fields=["contact_email", "updated_at"])
        if request.data.get("funding_wallet"):
            brand.funding_wallet = request.data["funding_wallet"].strip().lower()
            brand.save(update_fields=["funding_wallet", "updated_at"])
        return Response(BrandProfileSerializer(brand).data, status=status.HTTP_201_CREATED)

    brand = getattr(request.user, "brand_profile", None)
    if brand is None:
        return Response(
            {"detail": "No brand profile yet. POST your company name to create one."},
            status=status.HTTP_404_NOT_FOUND,
        )
    payload = BrandProfileSerializer(brand).data
    payload["funded_balance"] = str(confirmed_funded_balance(brand))
    return Response(payload)



@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def brand_funding(request):
    """List this brand's deposits, or record a new one.

    A recorded deposit starts PENDING and does not count toward the balance
    until it is confirmed against the chain. Recording is not crediting.
    """
    brand = getattr(request.user, "brand_profile", None)
    if brand is None:
        return Response(
            {"detail": "Create a brand profile before recording funding."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if request.method == "GET":
        deposits = BrandFunding.objects.filter(brand=brand)
        return Response(
            {
                "fundings": BrandFundingSerializer(deposits, many=True).data,
                "confirmed_balance": str(confirmed_funded_balance(brand)),
            }
        )

    try:
        funding = record_funding(
            brand,
            amount=request.data.get("amount"),
            chain_id=request.data.get("chain_id"),
            tx_hash=request.data.get("tx_hash"),
            token_symbol=request.data.get("token_symbol", funding_token_symbol()),
            actor=request.user,
        )
    except RewardEngineError as exc:
        return _error(exc)
    return Response(BrandFundingSerializer(funding).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def brand_funding_confirm(request, pk):
    """Confirm one of this brand's own deposits.

    Ownership is re-checked on the object, not just trusted from the URL: a
    brand must not be able to credit another brand's deposit by guessing an id.
    """
    brand = getattr(request.user, "brand_profile", None)
    if brand is None:
        return Response(
            {"detail": "Create a brand profile first."}, status=status.HTTP_400_BAD_REQUEST
        )
    funding = get_object_or_404(BrandFunding, pk=pk, brand=brand)
    try:
        funding = confirm_funding(funding, actor=request.user)
    except RewardEngineError as exc:
        return _error(exc)
    return Response(BrandFundingSerializer(funding).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def brand_quote(request):
    """Quote what a campaign of this size costs the brand, fee included."""
    brand = getattr(request.user, "brand_profile", None)
    if brand is None:
        return Response(
            {"detail": "Create a brand profile first."}, status=status.HTTP_400_BAD_REQUEST
        )
    try:
        payout_total = Decimal(str(request.data.get("payout_total")))
    except (TypeError, ValueError, ArithmeticError):
        return Response(
            {"payout_total": ["A numeric payout_total is required."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if payout_total <= 0:
        return Response(
            {"payout_total": ["Must be greater than zero."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    decimals = funding_token_decimals()
    quote = quote_campaign_cost(brand, payout_total=payout_total, decimals=decimals)
    quote["token_symbol"] = funding_token_symbol()
    quote["token_decimals"] = decimals
    return Response(quote)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def brand_campaigns(request):
    """Campaigns this brand is funding, with its funding position on each.

    A brand sees its own money, not other brands' campaigns: its funding
    history is what it is accountable for.
    """
    brand = getattr(request.user, "brand_profile", None)
    if brand is None:
        return Response(
            {"detail": "Create a brand profile first."}, status=status.HTTP_404_NOT_FOUND
        )

    campaigns = Campaign.objects.filter(fundings__brand=brand).distinct()
    return Response(
        {
            "campaigns": [
                {
                    "slug": campaign.slug,
                    "name": campaign.name,
                    "status": campaign.status,
                    "budget": str(campaign.budget),
                    "remaining_budget": str(campaign.remaining_budget),
                    "funded": str(confirmed_funded_balance(brand, campaign=campaign)),
                }
                for campaign in campaigns
            ],
            "confirmed_balance": str(confirmed_funded_balance(brand)),
        }
    )
