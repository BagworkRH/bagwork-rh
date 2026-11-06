"""Only verified accounts are tracked (Spec 03).

The rule reads like one line — an account with no verification badge has its
posts ignored — but three things about it are easy to get wrong, and each of them
is expensive: paying creators who should not have been paid, or refusing to pay
creators who should have been. So each has its own tests here.

  * **The wrong field.** X's legacy `verified` boolean reported `false` for
    Premium subscribers who had a visible blue badge (xurl issue #41, fixed in
    v1.2.0), while `verified_type` in the same response said "blue". A gate built
    on the boolean would refuse to pay real creators.
  * **The wrong lifetime.** X Premium is a *subscription*. A badge held when the
    account was connected can lapse with nothing on this side changing, so a
    connect-time check is farmable: subscribe for one month, connect, cancel,
    keep earning.
  * **The wrong failure direction.** When the badge cannot be established the
    safe answer is "not verified". An unreadable field must never default in the
    paying direction.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.social.crypto_utils import encrypt_secret
from apps.social.models import (
    VERIFIED_BADGE_TYPES,
    SocialAccount,
    SocialPlatform,
    SocialPost,
    normalize_verified_type,
)
from apps.social.providers.base import SocialProviderError
from apps.social.providers.mock import MockSocialProvider
from apps.social.services import (
    VERIFICATION_TTL,
    link_social_account,
    refresh_account_verification,
    verification_is_stale,
)
from apps.social.tasks import discover_posts_for_account

from .helpers import make_campaign, make_user


def connect_account(profile, *, verified_type="blue", **extra):
    """A connected X account, with encrypted credentials so it can be polled."""
    account = SocialAccount.objects.create(
        seller=profile,
        platform=SocialPlatform.X,
        provider_user_id="42",
        username="alice",
        status="CONNECTED",
        verified_type=verified_type,
        **extra,
    )
    creds, iv = encrypt_secret('{"access_token": "test-token"}')
    account.encrypted_credentials = creds
    account.credentials_iv = iv
    account.save(update_fields=["encrypted_credentials", "credentials_iv"])
    return account


class NormalizeVerifiedTypeTests(TestCase):
    """X's value is reduced to something we are willing to act on."""

    def test_the_badges_x_reports_are_accepted(self):
        # The documented enum, plus the case and padding a JSON payload can
        # arrive with.
        for raw in ("blue", "business", "government", "BLUE", " blue "):
            with self.subTest(raw=raw):
                self.assertIn(normalize_verified_type(raw), VERIFIED_BADGE_TYPES)

    def test_anything_else_means_no_badge(self):
        # Absent, explicitly-none, and anything X might add later. This value
        # decides whether someone is paid, so an unrecognised string cannot be
        # treated as a credential — the same reason an unrecognised
        # `referenced_tweets` type is treated as a repost, not an original.
        for raw in (None, "", "none", "None", "gold", "verified", "1", "True"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_verified_type(raw), "none")

    def test_is_verified_is_derived_not_stored(self):
        # Derived, so the badge and the boolean cannot drift apart.
        self.assertFalse(SocialAccount(verified_type="none").is_verified)
        self.assertFalse(SocialAccount(verified_type="gold").is_verified)
        self.assertTrue(SocialAccount(verified_type="blue").is_verified)
        self.assertTrue(SocialAccount(verified_type="business").is_verified)
        self.assertTrue(SocialAccount(verified_type="government").is_verified)


class ConnectRecordsTheBadgeTests(TestCase):
    """The badge enters the system at connect, recorded together with its age."""

    def setUp(self):
        self.user, self.profile = make_user()

    def _identity(self, **extra):
        return {
            "provider_user_id": "42",
            "username": "alice",
            "display_name": "Alice",
            "access_token": "tok",
            "refresh_token": "ref",
            "scopes": ["tweet.read"],
            **extra,
        }

    def test_connect_records_the_badge_and_when_it_was_read(self):
        account = link_social_account(self.profile, self._identity(verified_type="blue"))
        self.assertEqual(account.verified_type, "blue")
        self.assertTrue(account.is_verified)
        # The timestamp is what makes the badge expire. Without it the poller
        # could not tell a badge read a second ago from one read last year.
        self.assertIsNotNone(account.verification_checked_at)

    def test_connect_without_a_badge_records_none(self):
        # No `verified_type` in the identity, which is what X returns for an
        # account with no badge. Failing closed is the whole point.
        account = link_social_account(self.profile, self._identity())
        self.assertEqual(account.verified_type, "none")
        self.assertFalse(account.is_verified)

    def test_reconnecting_updates_a_changed_badge(self):
        link_social_account(self.profile, self._identity(verified_type="blue"))
        account = link_social_account(self.profile, self._identity(verified_type="none"))
        self.assertEqual(account.verified_type, "none")
        self.assertFalse(account.is_verified)


class UnverifiedAccountIsNotTrackedTests(TestCase):
    """A post is only trackable when its author carries a badge.

    Discovery reads the connected account's *own* timeline, so the author of
    every discovered post is that account. That is why this is a single gate on
    the account rather than a check on each post.
    """

    def setUp(self):
        self.user, self.profile = make_user()
        self.campaign = make_campaign(slug="verified-gate")
        self.account = connect_account(self.profile, verified_type="none")
        # Reports no badge, matching the stored account.
        self.provider = self._provider("none")

    def _provider(self, verified_type, post_id="111"):
        return MockSocialProvider(
            self.user,
            platform=SocialPlatform.X,
            discovered_posts=[
                {
                    "post_id": post_id,
                    "text": "my original post #ad",
                    "created_at": timezone.now() - timedelta(hours=1),
                }
            ],
            verified_type=verified_type,
        )

    def _poll(self, provider=None):
        provider = provider or self.provider
        with (
            patch("apps.social.providers.get_provider", return_value=provider),
            patch("apps.social.services.get_provider", return_value=provider),
            patch("apps.social.tasks.run_verification_on_post"),
        ):
            return discover_posts_for_account.apply(
                args=[self.account.pk, self.campaign.pk]
            ).get()

    def test_no_posts_are_created_for_an_unverified_account(self):
        result = self._poll()
        self.assertEqual(result["status"], "not-verified")
        self.assertEqual(result["created"], 0)
        self.assertEqual(SocialPost.objects.count(), 0)

    def test_the_provider_is_never_asked_for_an_unverified_account(self):
        # The gate sits before the timeline call, so an account that cannot be
        # tracked costs no API request at all.
        asked = []
        self.provider.discover_posts = lambda *args, **kwargs: asked.append(kwargs)
        self._poll()
        self.assertEqual(asked, [])

    def test_an_unverified_account_does_not_advance_the_watermark(self):
        # The watermark means "we have read up to here". Nothing was read, so
        # moving it forward would silently skip that window once the account
        # verifies.
        self._poll()
        self.campaign.refresh_from_db()
        self.assertIsNone(self.campaign.discovery_watermark(SocialPlatform.X))

    def test_a_verified_account_is_tracked(self):
        # The control. Every test above would also pass if discovery were simply
        # broken, so one test has to show the gate opening.
        result = self._poll(self._provider("blue", post_id="222"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["created"], 1)
        self.assertEqual(SocialPost.objects.filter(external_post_id="222").count(), 1)

    @override_settings(REQUIRE_VERIFIED_ACCOUNTS=False)
    def test_the_rule_can_be_switched_off(self):
        # A product decision, not a law of physics: the X badge is a paid
        # subscription, so requiring it excludes every creator who will not pay
        # for one. It has to be reversible without a code change.
        result = self._poll()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(SocialPost.objects.count(), 1)

    def test_a_provider_outage_does_not_strip_a_badge(self):
        # An outage must not read as "no badge", or a verified creator would stop
        # earning because X had a bad minute. The stored badge is left alone, this
        # poll is skipped, and the next tick asks again.
        self.account.verified_type = "blue"
        self.account.verification_checked_at = None  # force a re-read
        self.account.save(update_fields=["verified_type", "verification_checked_at"])

        def boom(*args, **kwargs):
            raise SocialProviderError("Account fetch failed: HTTP 503")

        self.provider.get_account = boom
        result = self._poll()

        self.assertEqual(result["status"], "provider-error")
        self.account.refresh_from_db()
        self.assertEqual(self.account.verified_type, "blue")
        self.assertEqual(SocialPost.objects.count(), 0)

    def test_a_lapsed_badge_stops_tracking(self):
        # Premium expires. Verified yesterday, not today, so tracking stops — and
        # the change is audited, because it changes whether someone gets paid.
        self.account.verified_type = "blue"
        self.account.verification_checked_at = (
            timezone.now() - VERIFICATION_TTL - timedelta(hours=1)
        )
        self.account.save(update_fields=["verified_type", "verification_checked_at"])

        result = self._poll()  # the provider now reports "none"

        self.assertEqual(result["status"], "not-verified")
        self.assertEqual(SocialPost.objects.count(), 0)
        self.account.refresh_from_db()
        self.assertEqual(self.account.verified_type, "none")
        self.assertTrue(
            AuditLog.objects.filter(action="SOCIAL_VERIFICATION_CHANGED").exists()
        )


class VerificationRefreshTests(TestCase):
    """Re-reading the badge must be bounded in cost, not only in correctness."""

    def setUp(self):
        self.user, self.profile = make_user()
        self.account = connect_account(
            self.profile, verified_type="blue", verification_checked_at=timezone.now()
        )

    def _provider(self, verified_type="blue"):
        provider = MockSocialProvider(
            self.user, platform=SocialPlatform.X, verified_type=verified_type
        )
        provider.calls = []
        original = provider.get_account

        def counting(token, *args, **kwargs):
            provider.calls.append(token)
            return original(token, *args, **kwargs)

        provider.get_account = counting
        return provider

    def test_a_fresh_badge_costs_nothing(self):
        # This runs before every poll, so inside the TTL it has to be a cache hit
        # rather than one API call per poll.
        provider = self._provider()
        with patch("apps.social.services.get_provider", return_value=provider):
            self.assertTrue(refresh_account_verification(self.account))
        self.assertEqual(provider.calls, [])

    def test_a_stale_badge_is_re_read(self):
        self.account.verification_checked_at = (
            timezone.now() - VERIFICATION_TTL - timedelta(minutes=1)
        )
        self.account.save(update_fields=["verification_checked_at"])
        provider = self._provider("business")
        with patch("apps.social.services.get_provider", return_value=provider):
            self.assertTrue(refresh_account_verification(self.account))
        self.assertEqual(len(provider.calls), 1)
        self.account.refresh_from_db()
        self.assertEqual(self.account.verified_type, "business")

    def test_force_re_reads_inside_the_ttl(self):
        provider = self._provider()
        with patch("apps.social.services.get_provider", return_value=provider):
            refresh_account_verification(self.account, force=True)
        self.assertEqual(len(provider.calls), 1)

    def test_staleness_boundary(self):
        # Stated explicitly because both sides are load-bearing: too eager spends
        # API calls, too lazy lets a lapsed badge keep earning.
        self.account.verification_checked_at = (
            timezone.now() - VERIFICATION_TTL + timedelta(minutes=5)
        )
        self.assertFalse(verification_is_stale(self.account))
        self.account.verification_checked_at = (
            timezone.now() - VERIFICATION_TTL - timedelta(minutes=5)
        )
        self.assertTrue(verification_is_stale(self.account))

    def test_an_account_never_checked_is_stale(self):
        # The state of every row created before this feature existed, so it has to
        # re-read rather than assume anything.
        self.account.verification_checked_at = None
        self.assertTrue(verification_is_stale(self.account))


class ConnectionsPayloadTests(TestCase):
    """The dashboard needs to be able to say why nothing is being tracked."""

    def setUp(self):
        self.client = APIClient()
        self.user, self.profile = make_user()
        self.client.force_authenticate(user=self.user)

    def test_reports_the_badge_and_the_policy(self):
        connect_account(self.profile, verified_type="none")
        # `reverse` rather than a literal: the social app is mounted at
        # /api/v1/x/ (the platform-agnostic routes included under an `x/`
        # segment, which is where the doubled `x` in X_REDIRECT_URI comes from).
        body = self.client.get(reverse("social:connections")).json()

        self.assertTrue(body["verified_accounts_required"])
        self.assertEqual(body["connections"][0]["verified_type"], "none")
        self.assertFalse(body["connections"][0]["is_verified"])
