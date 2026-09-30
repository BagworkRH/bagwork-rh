"""Campaign creation and editing tests (Stage 4).

A campaign is a promise about money. These tests cover the rules that keep that
promise honest: only fixed rewards, a budget that can actually pay someone, and
money terms that cannot be edited out from under a creator.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.campaigns.models import Campaign, CampaignStatus, RewardModel
from apps.campaigns.services import create_campaign
from apps.rewards.exceptions import RewardEngineError

from .helpers import make_staff, make_user


def _payload(**overrides):
    now = timezone.now()
    payload = {
        "name": "Launch",
        "slug": "api-launch",
        "project_name": "bagworkRH",
        "token_symbol": "RWD",
        "chain_id": 46630,
        "budget": "1000",
        "reward_model": RewardModel.FIXED,
        "reward_rate": "5",
        "start_at": (now - timedelta(days=1)).isoformat(),
        "end_at": (now + timedelta(days=30)).isoformat(),
        "requirements_json": {"required_hashtags": ["#ad"]},
    }
    payload.update(overrides)
    return payload


class CampaignCreateApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = make_staff()
        self.client.force_authenticate(self.staff)

    def test_staff_can_create_a_campaign(self):
        resp = self.client.post("/api/v1/campaigns/", _payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(Campaign.objects.filter(slug="api-launch").count(), 1)

    def test_created_campaign_has_full_remaining_budget(self):
        resp = self.client.post("/api/v1/campaigns/", _payload(), format="json")
        # The API serialises decimals as strings, at full 18-decimal precision.
        self.assertEqual(Decimal(resp.data["remaining_budget"]), Decimal("1000"))

    def test_created_campaign_starts_as_draft(self):
        # A campaign should not be joinable until deliberately launched.
        self.client.post("/api/v1/campaigns/", _payload(), format="json")
        self.assertEqual(
            Campaign.objects.get(slug="api-launch").status, CampaignStatus.DRAFT
        )

    def test_non_staff_cannot_create(self):
        self.client.force_authenticate(make_user()[0])
        resp = self.client.post("/api/v1/campaigns/", _payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_create(self):
        self.client.force_authenticate(None)
        resp = self.client.post("/api/v1/campaigns/", _payload(), format="json")
        self.assertIn(resp.status_code, (401, 403))

    def test_listing_stays_public(self):
        self.client.force_authenticate(None)
        resp = self.client.get("/api/v1/campaigns/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_impression_based_model_is_rejected(self):
        resp = self.client.post(
            "/api/v1/campaigns/",
            _payload(reward_model=RewardModel.IMPRESSION_BASED),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Campaign.objects.count(), 0)

    def test_budget_below_one_reward_is_rejected(self):
        # The important one: a creator who does real work and cannot be paid.
        resp = self.client.post(
            "/api/v1/campaigns/", _payload(budget="2", reward_rate="5"), format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Campaign.objects.count(), 0)

    def test_launch_publishes_the_campaign(self):
        self.client.post("/api/v1/campaigns/", _payload(), format="json")
        resp = self.client.post("/api/v1/campaigns/api-launch/launch/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Campaign.objects.get(slug="api-launch").status, CampaignStatus.ACTIVE
        )

    def test_launch_requires_staff(self):
        self.client.post("/api/v1/campaigns/", _payload(), format="json")
        # A distinct seller: make_staff is idempotent on email, so reusing the
        # default creator identity here would collide with the staff user.
        self.client.force_authenticate(make_user(email="seller@example.com")[0])
        resp = self.client.post("/api/v1/campaigns/api-launch/launch/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class CampaignEditApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = make_staff()
        self.client.force_authenticate(self.staff)
        self.client.post("/api/v1/campaigns/", _payload(), format="json")
        self.campaign = Campaign.objects.get(slug="api-launch")

    def test_draft_can_be_edited(self):
        resp = self.client.patch(
            "/api/v1/campaigns/api-launch/", {"description": "updated"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.description, "updated")

    def test_reward_rate_cannot_be_changed(self):
        # Changing the rate after creators joined would make already-calculated
        # rewards irreproducible.
        resp = self.client.patch(
            "/api/v1/campaigns/api-launch/", {"reward_rate": "500"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.reward_rate, Decimal("5"))

    def test_budget_cannot_be_changed(self):
        resp = self.client.patch(
            "/api/v1/campaigns/api-launch/", {"budget": "999999"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_active_campaign_cannot_be_edited(self):
        self.campaign.status = CampaignStatus.ACTIVE
        self.campaign.save(update_fields=["status"])
        resp = self.client.patch(
            "/api/v1/campaigns/api-launch/", {"description": "sneaky"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_paused_campaign_can_be_edited(self):
        self.campaign.status = CampaignStatus.PAUSED
        self.campaign.save(update_fields=["status"])
        resp = self.client.patch(
            "/api/v1/campaigns/api-launch/", {"description": "revised"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_non_staff_cannot_edit(self):
        self.client.force_authenticate(make_user()[0])
        resp = self.client.patch(
            "/api/v1/campaigns/api-launch/", {"description": "nope"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class CampaignServiceValidationTests(TestCase):
    """The rules live in the service so shell and admin obey them too."""

    def setUp(self):
        self.staff = make_staff()

    def test_zero_rate_is_rejected(self):
        with self.assertRaises(RewardEngineError):
            create_campaign(created_by=self.staff, **_payload(reward_rate="0"))

    def test_end_before_start_is_rejected(self):
        now = timezone.now()
        with self.assertRaises(RewardEngineError):
            create_campaign(
                created_by=self.staff,
                **_payload(
                    start_at=(now + timedelta(days=10)).isoformat(),
                    end_at=(now + timedelta(days=1)).isoformat(),
                ),
            )

    def test_surplus_beyond_the_post_cap_is_rejected(self):
        # 1000 budget at 5/post is 200 posts, but only 10 are allowed, so 990
        # could never be paid out.
        with self.assertRaises(RewardEngineError):
            create_campaign(
                created_by=self.staff, **_payload(maximum_rewards_per_seller=10)
            )

    def test_seller_cap_below_one_reward_is_rejected(self):
        with self.assertRaises(RewardEngineError):
            create_campaign(
                created_by=self.staff, **_payload(maximum_reward_per_seller="1")
            )

    def test_creation_is_audited(self):
        from apps.audit.models import AuditLog  # noqa: PLC0415

        create_campaign(created_by=self.staff, actor=self.staff, **_payload())
        self.assertTrue(AuditLog.objects.filter(action="CAMPAIGN_CREATED").exists())

    def test_service_refuses_non_fixed_model(self):
        with self.assertRaises(RewardEngineError):
            create_campaign(
                created_by=self.staff, **_payload(reward_model=RewardModel.HYBRID)
            )
