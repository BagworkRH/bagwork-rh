"""Social linking, post discovery and verification pipeline tests (Spec 03)."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

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


class SocialConnectionsEndpointTests(TestCase):
    """`GET /api/v1/x/connections/` must report linked accounts, and only yours.

    Separate from `platforms/`, which lists what this build *can* connect. A
    client needs to know what *is* connected before offering a disconnect --
    otherwise the only way to find out is to call disconnect and read the 404.
    """

    def setUp(self):
        self.client = APIClient()
        self.user, self.profile = make_user()

    def test_anonymous_cannot_list_connections(self):
        self.client.force_authenticate(None)
        resp = self.client.get("/api/v1/x/connections/")
        self.assertIn(resp.status_code, (401, 403))

    def test_seller_with_no_accounts_gets_an_empty_list(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/v1/x/connections/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["connections"], [])

    def test_linked_account_is_reported(self):
        SocialAccount.objects.create(
            seller=self.profile,
            platform=SocialPlatform.X,
            provider_user_id="42",
            username="seller",
        )
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/v1/x/connections/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rows = resp.data["connections"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["platform"], "x")
        self.assertEqual(rows[0]["username"], "seller")
        # Credential material must never cross the wire.
        self.assertNotIn("encrypted_credentials", rows[0])

    def test_only_returns_the_callers_own_accounts(self):
        """A second seller's link must not appear in this seller's list."""
        other_user, other_profile = make_user(
            email="other@example.com", username="other"
        )
        SocialAccount.objects.create(
            seller=other_profile,
            platform=SocialPlatform.X,
            provider_user_id="99",
            username="other-seller",
        )
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/v1/x/connections/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["connections"], [])
