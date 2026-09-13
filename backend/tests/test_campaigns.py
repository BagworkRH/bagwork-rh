"""Campaign eligibility and API tests (Spec 03)."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.campaigns.models import CampaignStatus
from apps.campaigns.services import join_campaign
from apps.rewards.exceptions import RewardEngineError
from apps.sellers.models import SellerProfile

from .helpers import make_campaign, make_user


class CampaignEligibilityTests(TestCase):
    def test_active_seller_can_join(self):
        user, profile = make_user()
        campaign = make_campaign()
        participation = join_campaign(profile, campaign, actor=user)
        self.assertEqual(participation.status, "ACTIVE")
        self.assertEqual(campaign.participations.count(), 1)

    def test_inactive_seller_rejected(self):
        user, profile = make_user()
        profile.status = SellerProfile.Status.SUSPENDED
        profile.save()
        campaign = make_campaign()
        with self.assertRaises(RewardEngineError):
            join_campaign(profile, campaign, actor=user)

    def test_draft_campaign_rejected(self):
        user, profile = make_user()
        campaign = make_campaign(status=CampaignStatus.DRAFT)
        with self.assertRaises(RewardEngineError):
            join_campaign(profile, campaign, actor=user)

    def test_ended_campaign_rejected(self):
        user, profile = make_user()
        campaign = make_campaign(end_at=timezone.now() - timedelta(days=1))
        with self.assertRaises(RewardEngineError):
            join_campaign(profile, campaign, actor=user)

    def test_future_campaign_rejected(self):
        user, profile = make_user()
        campaign = make_campaign(start_at=timezone.now() + timedelta(days=5))
        with self.assertRaises(RewardEngineError):
            join_campaign(profile, campaign, actor=user)

    def test_reputation_threshold(self):
        user, profile = make_user()
        profile.reputation_score = 10
        profile.save()
        campaign = make_campaign(requirements_json={"minimum_followers": 50})
        with self.assertRaises(RewardEngineError):
            join_campaign(profile, campaign, actor=user)

    def test_join_is_idempotent(self):
        user, profile = make_user()
        campaign = make_campaign()
        p1 = join_campaign(profile, campaign, actor=user)
        p2 = join_campaign(profile, campaign, actor=user)
        self.assertEqual(p1.pk, p2.pk)
        self.assertEqual(campaign.participations.count(), 1)