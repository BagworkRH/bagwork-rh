"""`GET /me/campaigns/` — the campaigns a seller has joined.

The public campaign list cannot answer this: it does not know who is asking, and
a seller's own view of a campaign carries their participation (when they joined,
what they have earned from it so far).
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.campaigns.models import CampaignParticipation, ParticipationStatus

from .helpers import make_campaign, make_user

User = get_user_model()


class MyCampaignsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user, self.profile = make_user()
        self.client.force_authenticate(self.user)
        self.campaign = make_campaign(name="Acme Launch", slug="acme-launch")

    def _join(self, campaign, **kwargs):
        return CampaignParticipation.objects.create(
            seller=self.profile, campaign=campaign, **kwargs
        )

    def test_lists_joined_campaigns_with_the_participation(self):
        self._join(self.campaign, cumulative_reward=Decimal("2.5"))

        resp = self.client.get("/api/v1/me/campaigns/")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        row = resp.data[0]
        self.assertEqual(row["campaign_id"], self.campaign.pk)
        self.assertEqual(row["slug"], "acme-launch")
        self.assertEqual(row["name"], "Acme Launch")
        self.assertEqual(row["campaign_status"], "ACTIVE")
        self.assertEqual(row["participation_status"], ParticipationStatus.ACTIVE)
        self.assertEqual(Decimal(row["cumulative_reward"]), Decimal("2.5"))
        self.assertEqual(Decimal(row["reward_rate"]), Decimal("5"))

    def test_empty_for_a_seller_who_has_joined_nothing(self):
        resp = self.client.get("/api/v1/me/campaigns/")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, [])

    def test_only_returns_the_callers_own_participations(self):
        # A campaign another seller joined must not appear on this seller's page.
        other_user, other_profile = make_user(email="other@example.com", username="other")
        CampaignParticipation.objects.create(seller=other_profile, campaign=self.campaign)
        mine = make_campaign(name="Mine", slug="mine")
        self._join(mine)

        resp = self.client.get("/api/v1/me/campaigns/")

        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["slug"], "mine")

    def test_most_recently_joined_first(self):
        first = make_campaign(name="First", slug="first")
        second = make_campaign(name="Second", slug="second")
        now = timezone.now()
        self._join(first, joined_at=now - timedelta(days=2))
        self._join(second, joined_at=now)

        resp = self.client.get("/api/v1/me/campaigns/")

        self.assertEqual([r["slug"] for r in resp.data], ["second", "first"])

    def test_requires_authentication(self):
        resp = APIClient().get("/api/v1/me/campaigns/")

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_user_without_a_seller_profile_is_a_404(self):
        user = User.objects.create_user(
            username="noseller", email="noseller@example.com", password="Testpass123!"
        )
        client = APIClient()
        client.force_authenticate(user)

        resp = client.get("/api/v1/me/campaigns/")

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
