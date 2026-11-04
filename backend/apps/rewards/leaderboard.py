"""The public leaderboard (Spec 03).

An arena built on data we already have: what each creator earned in a campaign.
Public on purpose - the board is the platform's own proof that it pays, and a
visitor deciding whether to join has exactly one question that a percentage
cannot answer: does this actually pay anyone?

Three rules make publishing money safe rather than reckless:

  * only *settled* rewards count. PENDING and VERIFIED are proposals staff may
    still reverse, and publishing a figure we might take back is worse than
    publishing nothing.
  * a creator who hides their earnings keeps their rank and loses only the
    figure.
  * wallet addresses are never included. A payout being public is the point; an
    address to attack is not.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.campaigns.models import Campaign
from apps.sellers.models import SellerProfile
from apps.social.models import SocialAccount

from .models import Reward, RewardStatus

SETTLED = (RewardStatus.APPROVED, RewardStatus.AVAILABLE, RewardStatus.CLAIMED)

SERIES_DAYS = 30
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
ZERO = Decimal("0")


def _campaign_or_default(slug):
    """The requested campaign, or the busiest one that has actually paid."""
    if slug:
        return get_object_or_404(Campaign, slug=slug)
    busiest = (
        Campaign.objects.filter(rewards__status__in=SETTLED)
        .annotate(settled=Count("rewards"))
        .order_by("-settled", "-id")
        .first()
    )
    return busiest or Campaign.objects.order_by("-id").first()


def _daily_series(settled, days):
    """{seller_id: [per-day totals]}, oldest first, for the sparklines."""
    start = timezone.now().date() - timedelta(days=days - 1)
    series = {}
    rows = (
        settled.filter(approved_at__date__gte=start)
        .annotate(day=TruncDate("approved_at"))
        .values("seller_id", "day")
        .annotate(total=Sum("amount"))
    )
    for row in rows:
        offset = (row["day"] - start).days
        if 0 <= offset < days:
            series.setdefault(row["seller_id"], [ZERO] * days)[offset] = row["total"]
    return series


def _page_bounds(request):
    try:
        limit = min(int(request.query_params.get("limit", DEFAULT_LIMIT)), MAX_LIMIT)
        offset = max(int(request.query_params.get("offset", 0)), 0)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT, 0
    return max(limit, 1), offset


@api_view(["GET"])
@permission_classes([AllowAny])
def leaderboard(request):
    """Ranked creators for one campaign, with their earnings and deltas."""
    campaign = _campaign_or_default(request.query_params.get("campaign"))
    if campaign is None:
        return Response(
            {
                "campaign": None,
                "totals": {"creators": 0, "rewards": 0, "paid": "0"},
                "series_days": SERIES_DAYS,
                "entries": [],
            }
        )

    limit, offset = _page_bounds(request)
    settled = Reward.objects.filter(campaign=campaign, status__in=SETTLED)

    totals = settled.aggregate(paid=Sum("amount"), rewards=Count("id"))
    total_paid = totals["paid"] or ZERO

    ranked = list(
        settled.values("seller_id")
        .annotate(earned=Sum("amount"), rewards=Count("id"), last=Max("approved_at"))
        .order_by("-earned", "seller_id")
    )

    now = timezone.now()
    deltas = {
        row["seller_id"]: row
        for row in settled.values("seller_id").annotate(
            d7=Sum("amount", filter=Q(approved_at__gte=now - timedelta(days=7))),
            d30=Sum("amount", filter=Q(approved_at__gte=now - timedelta(days=30))),
        )
    }
    series = _daily_series(settled, SERIES_DAYS)

    page = ranked[offset : offset + limit]
    ids = [row["seller_id"] for row in page]
    profiles = SellerProfile.objects.filter(id__in=ids).in_bulk()
    # One account per creator: the first linked one is the identity we show.
    accounts = {}
    for account in SocialAccount.objects.filter(seller_id__in=ids).order_by("id"):
        accounts.setdefault(account.seller_id, account)

    entries = []
    for position, row in enumerate(page, start=offset + 1):
        profile = profiles.get(row["seller_id"])
        if profile is None:
            continue
        account = accounts.get(row["seller_id"])
        entry = {
            "rank": position,
            "display_name": profile.display_name
            or (account.username if account else "Creator"),
            "username": account.username if account else None,
            "avatar_url": account.avatar_url if account else "",
            "rewards": row["rewards"],
            "hidden": not profile.show_earnings_publicly,
            "demo": profile.is_demo,
        }
        if profile.show_earnings_publicly:
            earned = row["earned"]
            entry.update(
                {
                    "earned": str(earned),
                    "share": float(earned / total_paid) if total_paid else 0.0,
                    "delta_7d": str(deltas.get(row["seller_id"], {}).get("d7") or ZERO),
                    "delta_30d": str(deltas.get(row["seller_id"], {}).get("d30") or ZERO),
                    "series": [
                        float(value) for value in series.get(row["seller_id"], [])
                    ]
                    or [0.0] * SERIES_DAYS,
                }
            )
        else:
            entry.update(
                {
                    "earned": None,
                    "share": None,
                    "delta_7d": None,
                    "delta_30d": None,
                    "series": [],
                }
            )
        entries.append(entry)

    return Response(
        {
            "campaign": {
                "slug": campaign.slug,
                "name": campaign.name,
                "token_symbol": campaign.token_symbol,
                "status": campaign.status,
                "reward_rate": str(campaign.reward_rate),
                "budget": str(campaign.budget),
                "remaining_budget": str(campaign.remaining_budget),
                "start_at": campaign.start_at,
                "end_at": campaign.end_at,
            },
            "totals": {
                "creators": len(ranked),
                "rewards": totals["rewards"] or 0,
                "paid": str(total_paid),
            },
            "series_days": SERIES_DAYS,
            # Lets the page say so, rather than leaving a visitor to work out
            # from the campaign name whether these are real payouts.
            "has_demo": any(entry["demo"] for entry in entries),
            "entries": entries,
        }
    )


def _rank_in_campaign(campaign_id, seller_id):
    """(rank, entrants) for one creator in one campaign."""
    rows = list(
        Reward.objects.filter(campaign_id=campaign_id, status__in=SETTLED)
        .values("seller_id")
        .annotate(earned=Sum("amount"))
        .order_by("-earned", "seller_id")
    )
    for position, row in enumerate(rows, start=1):
        if row["seller_id"] == seller_id:
            return position, len(rows)
    return None, len(rows)


@api_view(["GET"])
@permission_classes([AllowAny])
def creator_card(request, seller_code):
    """One creator's public earnings card, for sharing.

    This is the distribution loop: a creator who has been paid shares proof, and
    the proof is what recruits the next creator. It reports the same facts as the
    leaderboard and obeys the same opt-out - a creator who hid their earnings
    keeps their rank and standing, and the figures are simply absent, rather than
    handing them a card with nothing on it.
    """
    profile = get_object_or_404(SellerProfile, seller_code=seller_code)
    account = SocialAccount.objects.filter(seller=profile).order_by("id").first()
    settled = Reward.objects.filter(seller=profile, status__in=SETTLED)

    totals = settled.aggregate(
        paid=Sum("amount"), rewards=Count("id"), campaigns=Count("campaign", distinct=True)
    )
    best = (
        settled.values("campaign__slug", "campaign__name", "campaign__token_symbol")
        .annotate(paid=Sum("amount"), rewards=Count("id"))
        .order_by("-paid", "campaign__slug")
        .first()
    )

    card = {
        "seller_code": profile.seller_code,
        "display_name": profile.display_name or (account.username if account else "Creator"),
        "username": account.username if account else None,
        "avatar_url": account.avatar_url if account else "",
        "hidden": not profile.show_earnings_publicly,
        "demo": profile.is_demo,
        "campaigns": totals["campaigns"] or 0,
        "rewards": totals["rewards"] or 0,
        "best_campaign": None,
    }

    if best:
        campaign_id = (
            Reward.objects.filter(
                seller=profile, status__in=SETTLED, campaign__slug=best["campaign__slug"]
            )
            .values_list("campaign_id", flat=True)
            .first()
        )
        rank, entrants = _rank_in_campaign(campaign_id, profile.id)
        card["best_campaign"] = {
            "slug": best["campaign__slug"],
            "name": best["campaign__name"],
            "token_symbol": best["campaign__token_symbol"],
            "rank": rank,
            "entrants": entrants,
        }

    if profile.show_earnings_publicly:
        now = timezone.now()
        deltas = settled.aggregate(
            d7=Sum("amount", filter=Q(approved_at__gte=now - timedelta(days=7))),
            d30=Sum("amount", filter=Q(approved_at__gte=now - timedelta(days=30))),
        )
        series = _daily_series(settled, SERIES_DAYS).get(profile.id, [])
        card.update(
            {
                "paid": str(totals["paid"] or ZERO),
                "delta_7d": str(deltas["d7"] or ZERO),
                "delta_30d": str(deltas["d30"] or ZERO),
                "series": [float(value) for value in series] or [0.0] * SERIES_DAYS,
            }
        )
    else:
        card.update({"paid": None, "delta_7d": None, "delta_30d": None, "series": []})

    return Response(card)
