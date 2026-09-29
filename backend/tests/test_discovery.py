"""Discovery tests (Stage 3).

The product is automatic: a creator links an account, posts, and gets paid with
no manual step. These tests cover the two properties that make that safe --
discovery actually finds and creates posts, and polling repeatedly does not
create duplicates or lose posts across an outage.
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.campaigns.models import CampaignStatus
from apps.social.crypto_utils import encrypt_secret
from apps.social.models import (
    OriginalityEvidence,
    PostVerificationStatus,
    SocialAccount,
    SocialPlatform,
    SocialPost,
)
from apps.social.providers.base import SocialProviderError
from apps.social.providers.mock import MockSocialProvider
from apps.social.providers.official import OfficialXProvider, _rfc3339
from apps.social.providers.tiktok import OfficialTikTokProvider, _epoch_millis
from apps.social.tasks import discover_posts_for_account, run_verification_on_post

from .helpers import make_campaign, make_user

X_TIMELINE = {
    "data": [
        {
            "id": "111",
            "text": "my original post #ad",
            "created_at": "2026-09-01T12:00:00.000Z",
        },
        {
            "id": "222",
            "text": "a repost of someone else #ad",
            "created_at": "2026-09-01T13:00:00.000Z",
            "referenced_tweets": [{"type": "reposted", "id": "999"}],
        },
    ]
}


def _response(payload):
    """Minimal stand-in for a requests.Response."""
    return SimpleNamespace(ok=True, json=lambda: payload, status_code=200)


class XDiscoveryRequestTests(TestCase):
    """The request must match the endpoint X actually documents."""

    def test_uses_the_renamed_timeline_endpoint(self):
        # X moved this to /2/users/:id/timelines/reverse_chronological in
        # v2.168. The old /2/users/:id/tweets path no longer exists.
        campaign = make_campaign(slug="x-discovery")
        captured = {}

        def fake_get(url, headers=None, params=None, timeout=None):
            captured["url"] = url
            captured["params"] = params
            return _response(X_TIMELINE)

        with (
            patch.object(
                OfficialXProvider, "get_account", return_value={"provider_user_id": "42"}
            ),
            patch("apps.social.providers.official.requests.get", side_effect=fake_get),
        ):
            found = OfficialXProvider().discover_posts(
                "tok", "42", campaign, campaign.start_at, timezone.now()
            )

        self.assertIn("/2/users/42/timelines/reverse_chronological", captured["url"])
        # `exclude` keeps results to original posts; originality is still
        # re-derived from referenced_tweets rather than trusted.
        self.assertEqual(captured["params"]["exclude"], "retweets,replies")
        self.assertEqual(captured["params"]["max_results"], 100)
        self.assertIn("referenced_tweets", captured["params"]["tweet.fields"])
        self.assertEqual(len(found), 2)
        self.assertFalse(found[0]["is_repost"])
        self.assertTrue(found[1]["is_repost"])

    def test_window_bounded_by_campaign_when_no_watermark(self):
        campaign = make_campaign(slug="x-window")
        captured = {}

        def fake_get(url, headers=None, params=None, timeout=None):
            captured["params"] = params
            return _response({"data": []})

        with (
            patch.object(
                OfficialXProvider, "get_account", return_value={"provider_user_id": "42"}
            ),
            patch("apps.social.providers.official.requests.get", side_effect=fake_get),
        ):
            OfficialXProvider().discover_posts("tok", "42", campaign, None, None)
        self.assertTrue(captured["params"]["start_time"].endswith("Z"))
        self.assertTrue(captured["params"]["end_time"].endswith("Z"))

    def test_timestamps_are_rfc3339(self):
        self.assertTrue(_rfc3339(timezone.now()).endswith("Z"))
        self.assertEqual(_rfc3339(None), "")


class TikTokDiscoveryTests(TestCase):
    """TikTok's List Videos uses a millisecond cursor, not a date string."""

    def test_uses_video_list_endpoint(self):
        campaign = make_campaign(slug="tt-discovery")
        captured = {}
        # Inside the campaign window, which ends "now".
        created = int((timezone.now() - timedelta(hours=1)).timestamp())

        def fake_post(url, headers=None, params=None, json=None, timeout=None):
            captured["url"] = url
            captured["body"] = json
            return _response(
                {
                    "data": {
                        "videos": [
                            {"id": "999", "title": "hey #ad", "create_time": created}
                        ],
                        "has_more": False,
                    }
                }
            )

        with patch("apps.social.providers.tiktok.requests.post", side_effect=fake_post):
            found = OfficialTikTokProvider().discover_posts(
                "tok", "open-id", campaign, campaign.start_at, timezone.now()
            )
        self.assertIn("/v2/video/list/", captured["url"])
        self.assertEqual(captured["body"]["max_count"], 20)
        self.assertEqual(len(found), 1)
        # A TikTok video is the creator's own upload: original by construction.
        self.assertFalse(found[0]["is_repost"])
        self.assertIsNotNone(found[0]["created_at"].tzinfo)

    def test_cursor_is_epoch_millis(self):
        self.assertIsNone(_epoch_millis(None))
        self.assertIsInstance(_epoch_millis(timezone.now()), int)

    def test_normalize_reads_unix_seconds(self):
        payload = OfficialTikTokProvider.normalize_video(
            {"id": "1", "title": "t", "create_time": 1757000000, "share_url": "u"}
        )
        self.assertEqual(payload["post_id"], "1")
        self.assertEqual(payload["text"], "t")
        self.assertEqual(payload["post_url"], "u")


class DiscoveryPollerTests(TestCase):
    """Polling runs forever, so it must be safe to repeat and safe to fail."""

    def setUp(self):
        self.user, self.profile = make_user()
        self.campaign = make_campaign(slug="poller")
        self.account = SocialAccount.objects.create(
            seller=self.profile,
            platform=SocialPlatform.X,
            provider_user_id="42",
            username="alice",
            status="CONNECTED",
        )
        creds, iv = encrypt_secret('{"access_token": "test-token"}')
        self.account.encrypted_credentials = creds
        self.account.credentials_iv = iv
        self.account.save(update_fields=["encrypted_credentials", "credentials_iv"])
        # A publication time is mandatory: a post with no timestamp cannot be
        # placed in a campaign window, so discovery refuses it outright.
        self.in_window = timezone.now() - timedelta(hours=1)

    def _post(self, post_id, **extra):
        return {
            "post_id": post_id,
            "text": "original #ad",
            "created_at": self.in_window,
            **extra,
        }

    def _poll(self, found=None, error=None):
        provider = MockSocialProvider(
            self.user, platform=SocialPlatform.X, discovered_posts=found or []
        )
        if error:

            def boom(*args, **kwargs):
                raise error

            provider.discover_posts = boom
        # get_provider is imported inside the task, so the registry module is
        # the correct patch target.
        with patch("apps.social.providers.get_provider", return_value=provider):
            return discover_posts_for_account.apply(
                args=[self.account.pk, self.campaign.pk]
            ).get()

    def test_creates_post_with_provider_confirmed_originality(self):
        result = self._poll([self._post("111")])
        self.assertEqual(result["created"], 1)
        post = SocialPost.objects.get(external_post_id="111")
        # Discovery is a provider fact, so the post can actually earn.
        self.assertEqual(post.originality_evidence, OriginalityEvidence.PROVIDER_CONFIRMED)
        self.assertEqual(post.verification_status, PostVerificationStatus.DISCOVERED)

    def test_discovered_post_verifies_and_can_earn(self):
        self.campaign.requirements_json = {"required_hashtags": ["#ad"]}
        self.campaign.save(update_fields=["requirements_json"])
        self._poll([self._post("112")])
        post = SocialPost.objects.get(external_post_id="112")
        result = run_verification_on_post.apply(args=[post.pk]).get()
        self.assertEqual(result["status"], PostVerificationStatus.VERIFIED)

    def test_polling_twice_does_not_duplicate(self):
        found = [self._post("113")]
        self._poll(found)
        second = self._poll(found)
        self.assertEqual(second["created"], 0)
        self.assertEqual(SocialPost.objects.filter(external_post_id="113").count(), 1)

    def test_watermark_advances_on_success(self):
        self.assertIsNone(self.campaign.discovery_watermark(SocialPlatform.X))
        self._poll([])
        self.campaign.refresh_from_db()
        self.assertIsNotNone(self.campaign.discovery_watermark(SocialPlatform.X))

    def test_watermark_is_per_platform(self):
        self._poll([])
        self.campaign.refresh_from_db()
        self.assertIsNone(self.campaign.discovery_watermark(SocialPlatform.TIKTOK))

    def test_provider_error_does_not_advance_the_watermark(self):
        # If we advanced it on failure, a transient outage would silently
        # discard every post published during the gap.
        result = self._poll(error=SocialProviderError("boom"))
        self.assertEqual(result["status"], "provider-error")
        self.campaign.refresh_from_db()
        self.assertIsNone(self.campaign.discovery_watermark(SocialPlatform.X))

    def test_repost_discovered_is_recorded_as_provider_rejected(self):
        self._poll([self._post("114", text="rt #ad", is_repost=True)])
        post = SocialPost.objects.get(external_post_id="114")
        self.assertEqual(post.originality_evidence, OriginalityEvidence.PROVIDER_REJECTED)
        self.assertFalse(post.is_original)

    def test_inactive_campaign_is_skipped(self):
        self.campaign.status = CampaignStatus.PAUSED
        self.campaign.save(update_fields=["status"])
        result = self._poll([self._post("115")])
        self.assertEqual(result["status"], "inactive")
        self.assertEqual(SocialPost.objects.count(), 0)

    def test_disconnected_account_is_skipped(self):
        self.account.status = "DISCONNECTED"
        self.account.save(update_fields=["status"])
        result = self._poll([self._post("116")])
        self.assertEqual(result["status"], "inactive")
        self.assertEqual(SocialPost.objects.count(), 0)

    def test_discovery_respects_beat_schedule(self):
        from django.conf import settings  # noqa: PLC0415

        entry = settings.CELERY_BEAT_SCHEDULE["poll-social-discovery"]
        self.assertEqual(entry["task"], "apps.social.tasks.poll_active_campaigns")
