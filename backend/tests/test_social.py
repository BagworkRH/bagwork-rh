"""Social linking, post discovery and verification pipeline tests (Spec 03)."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.social.models import (
    OriginalityEvidence,
    PostMetricSnapshot,
    PostVerificationStatus,
    SocialAccount,
    SocialPlatform,
    SocialPost,
)
from apps.social.post_services import create_post_from_provider, run_verification

from .helpers import make_campaign, make_user


class SocialAccountLinkingTests(TestCase):
    def test_link_and_disconnect(self):
        user, profile = make_user()
        account = SocialAccount.objects.create(
            seller=profile,
            platform=SocialPlatform.X,
            provider_user_id="u-1",
            username="alice",
            display_name="Alice",
            status="CONNECTED",
        )
        self.assertEqual(account.seller, profile)
        self.assertEqual(account.status, "CONNECTED")
        account.status = "DISCONNECTED"
        account.save()
        self.assertEqual(account.status, "DISCONNECTED")

    def test_same_provider_id_coexists_across_platforms(self):
        # X and TikTok both issue numeric ids, so identity must be scoped to
        # the platform or linking one would silently overwrite the other.
        user, profile = make_user()
        SocialAccount.objects.create(
            seller=profile, platform=SocialPlatform.X, provider_user_id="777",
            username="alice",
        )
        tiktok = SocialAccount.objects.create(
            seller=profile, platform=SocialPlatform.TIKTOK, provider_user_id="777",
            username="alice",
        )
        self.assertEqual(SocialAccount.objects.filter(seller=profile).count(), 2)
        self.assertEqual(tiktok.provider_user_id, "777")

    def test_seller_cannot_link_same_platform_twice(self):
        user, profile = make_user()
        SocialAccount.objects.create(
            seller=profile, platform=SocialPlatform.X, provider_user_id="1", username="a"
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            SocialAccount.objects.create(
                seller=profile, platform=SocialPlatform.X, provider_user_id="2", username="b"
            )


class PostDiscoveryTests(TestCase):
    def test_discovered_post_created_with_unique_id(self):
        user, profile = make_user()
        campaign = make_campaign()
        payload = {
            "post_id": "p-123",
            "text": "#campaign promo",
            "created_at": timezone.now().isoformat(),
            "post_url": "https://x.com/status/p-123",
        }
        post = create_post_from_provider(profile, campaign, payload, actor=user)
        self.assertEqual(post.external_post_id, "p-123")
        self.assertEqual(post.verification_status, PostVerificationStatus.DISCOVERED)

    def test_duplicate_post_rejected(self):
        user, profile = make_user()
        campaign = make_campaign()
        payload = {
            "post_id": "p-dup",
            "text": "#campaign",
            "created_at": timezone.now().isoformat(),
            "post_url": "https://x.com/status/p-dup",
        }
        create_post_from_provider(profile, campaign, payload, actor=user)
        duplicate = create_post_from_provider(profile, campaign, payload, actor=user)
        self.assertIsNone(duplicate)

    def test_post_outside_campaign_window_rejected(self):
        user, profile = make_user()
        campaign = make_campaign()
        post = SocialPost.objects.create(
            external_post_id="p-out",
            seller=profile,
            campaign=campaign,
            post_url="https://x.com/status/p-out",
            text_snapshot="#campaign",
            # Published before campaign start
            published_at=campaign.start_at - timedelta(days=2),
            verification_status=PostVerificationStatus.DISCOVERED,
        )
        result = run_verification(post, actor=user)
        self.assertEqual(result.verification_status, PostVerificationStatus.OUTSIDE_CAMPAIGN_WINDOW)

    def test_missing_hashtag_rejected(self):
        user, profile = make_user()
        campaign = make_campaign(requirements_json={"required_hashtags": ["#promo"]})
        post = SocialPost.objects.create(
            external_post_id="p-hash",
            seller=profile,
            campaign=campaign,
            post_url="https://x.com/status/p-hash",
            text_snapshot="no hashtag here",
            published_at=timezone.now(),
            verification_status=PostVerificationStatus.DISCOVERED,
            originality_evidence=OriginalityEvidence.PROVIDER_CONFIRMED,
        )
        result = run_verification(post, actor=user)
        self.assertEqual(result.verification_status, PostVerificationStatus.REQUIREMENT_MISSING)

    def test_verification_creates_snapshot(self):
        user, profile = make_user()
        campaign = make_campaign(requirements_json={"required_hashtags": ["#campaign"]})
        post = SocialPost.objects.create(
            external_post_id="p-ok",
            seller=profile,
            campaign=campaign,
            post_url="https://x.com/status/p-ok",
            text_snapshot="hello #campaign",
            published_at=timezone.now(),
            verification_status=PostVerificationStatus.DISCOVERED,
            originality_evidence=OriginalityEvidence.PROVIDER_CONFIRMED,
        )
        result = run_verification(
            post,
            snapshot={
                "impressions": 1000,
                "likes": 10,
                "reposts": 5,
                "replies": 2,
                "quotes": 0,
                "bookmarks": 0,
                "collected_at": timezone.now(),
            },
            actor=user,
        )
        self.assertEqual(result.verification_status, PostVerificationStatus.VERIFIED)
        self.assertTrue(PostMetricSnapshot.objects.filter(post=post).exists())