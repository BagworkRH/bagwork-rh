"""Trust-boundary tests for the fixed-reward model (Spec 03).

Two things must hold for "a fixed reward per verified original post" to mean
anything:

1. A post's identity is (platform, external_post_id), so an id collision
   across platforms is not treated as a duplicate.
2. Originality comes from the platform, not from what the seller typed.
"""
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.social.crypto_utils import encrypt_secret
from apps.social.models import (
    PostVerificationStatus,
    SocialAccount,
    SocialPlatform,
    SocialPost,
)
from apps.social.providers.official import OfficialXProvider
from apps.social.tasks import refresh_post_facts

from .helpers import make_campaign, make_user

SHARED_ID = "5551234567890"


class SubmitPlatformScopingTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_user()
        self.campaign = make_campaign(slug="platform-scoping")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _submit(self, platform):
        return self.client.post(
            "/api/v1/posts/submit/",
            {
                "campaign": self.campaign.slug,
                "external_post_id": SHARED_ID,
                "text": "hello #ad",
                "post_url": f"https://example.com/{platform}/{SHARED_ID}",
                "published_at": timezone.now().isoformat(),
                "platform": platform,
            },
            format="json",
        )

    def test_same_id_on_two_platforms_are_not_duplicates(self):
        # Regression: the submit endpoint filtered on external_post_id alone,
        # so a TikTok post was rejected as a duplicate of an X post that
        # happened to share its numeric id.
        x_resp = self._submit(SocialPlatform.X)
        self.assertEqual(x_resp.status_code, status.HTTP_201_CREATED)
        tt_resp = self._submit(SocialPlatform.TIKTOK)
        self.assertEqual(tt_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SocialPost.objects.count(), 2)

    def test_same_id_on_same_platform_is_still_a_duplicate(self):
        self._submit(SocialPlatform.X)
        again = self._submit(SocialPlatform.X)
        self.assertEqual(again.status_code, status.HTTP_409_CONFLICT)

    def test_unknown_platform_is_rejected(self):
        resp = self._submit("myspace")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_response_exposes_platform_and_originality(self):
        resp = self._submit(SocialPlatform.TIKTOK)
        self.assertEqual(resp.data["platform"], SocialPlatform.TIKTOK)
        self.assertIn("is_original", resp.data)


class ProviderFactRefreshTests(TestCase):
    """The platform's record must overwrite the seller's claims."""

    def setUp(self):
        self.user, self.profile = make_user()
        self.campaign = make_campaign(slug="fact-refresh")
        # A post is only re-checkable when its author has a connected account;
        # without credentials the provider cannot be queried.
        self.account = SocialAccount.objects.create(
            seller=self.profile,
            platform=SocialPlatform.X,
            provider_user_id="acct-1",
            username="alice",
            status="CONNECTED",
        )
        self.post = SocialPost.objects.create(
            seller=self.profile,
            account=self.account,
            campaign=self.campaign,
            platform=SocialPlatform.X,
            external_post_id="999000111",
            post_url="https://x.com/i/status/999000111",
            # A seller-claimed original post that is actually a repost.
            text_snapshot="my brilliant original #ad",
            published_at=timezone.now(),
        )
        # A connected account always has encrypted credentials, so make this
        # one real enough to decrypt in the task.
        creds, iv = encrypt_secret('{"access_token": "test-token"}')
        self.account.encrypted_credentials = creds
        self.account.credentials_iv = iv
        self.account.save(update_fields=["encrypted_credentials", "credentials_iv"])

    def test_no_account_is_a_noop(self):
        orphan = SocialPost.objects.create(
            seller=self.profile,
            campaign=self.campaign,
            platform=SocialPlatform.X,
            external_post_id="orphan-1",
            post_url="https://x.com/i/status/orphan-1",
            text_snapshot="x",
            published_at=timezone.now(),
        )
        result = refresh_post_facts.apply(args=[orphan.pk]).get()
        self.assertEqual(result["status"], "no-connected-account")

    def _run(self, raw):
        """Re-fetch `self.post` from a provider stubbed to return `raw`."""
        with patch.object(OfficialXProvider, "get_post", return_value=raw):
            return refresh_post_facts.apply(args=[self.post.pk]).get()

    def test_provider_repost_overwrites_the_claim(self):
        result = self._run(
            {
                "id": "999000111",
                "text": "actually a repost",
                "referenced_tweets": [{"type": "retweeted", "id": "42"}],
            }
        )
        self.post.refresh_from_db()
        self.assertIn("is_repost", result["updated"])
        self.assertTrue(self.post.is_repost)
        self.assertFalse(self.post.is_original)

    def test_provider_text_overwrites_the_claim(self):
        self._run({"id": "999000111", "text": "actual text from the platform"})
        self.post.refresh_from_db()
        self.assertEqual(self.post.text_snapshot, "actual text from the platform")

    def test_missing_post_is_flagged_not_silently_trusted(self):
        self._run({})
        self.post.refresh_from_db()
        self.assertEqual(self.post.verification_status, PostVerificationStatus.PROVIDER_ERROR)

    def test_refreshed_repost_fails_verification(self):
        # The end-to-end guarantee: a repost cannot earn even when the seller
        # submitted it as original. The fixture must use the type X actually
        # returns (`retweeted`); while it said "reposted" this test passed
        # against a value the live API never sends, so it proved nothing.
        self._run(
            {
                "id": "999000111",
                "text": "my brilliant original #ad",
                "referenced_tweets": [{"type": "retweeted", "id": "42"}],
            }
        )
        self.post.refresh_from_db()
        from apps.social.post_services import run_verification  # noqa: PLC0415

        run_verification(self.post)
        self.assertEqual(self.post.verification_status, PostVerificationStatus.NOT_ORIGINAL)
