"""The public leaderboard (Spec 03).

The board exists to answer the one question a visitor has - does this actually
pay anyone? - so these tests are about what it publishes: settled money only,
never a figure a creator asked to keep private, and never a wallet address.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.campaigns.models import Campaign
from apps.rewards.models import Reward, RewardStatus
from apps.sellers.models import SellerProfile
from apps.social.models import SocialAccount, SocialPlatform

from .helpers import make_campaign, make_user

URL = "/api/v1/leaderboard/"


def _reward(seller, campaign, amount, status=RewardStatus.APPROVED, days_ago=0):
    """A reward dated in the past, so deltas and the sparkline have shape."""
    when = timezone.now() - timedelta(days=days_ago)
    reward = Reward.objects.create(
        seller=seller,
        campaign=campaign,
        amount=Decimal(amount),
        gross_amount=Decimal(amount),
        token_symbol="USDG",
        chain_id=46630,
        status=status,
    )
    Reward.objects.filter(pk=reward.pk).update(approved_at=when, created_at=when)
    return reward


def _creator(username, email):
    """A creator with a linked account, which is the identity the board shows."""
    _user, profile = make_user(email=email, username=username)
    SocialAccount.objects.create(
        seller=profile,
        platform=SocialPlatform.X,
        provider_user_id=username,
        username=username,
        avatar_url=f"https://img.example/{username}.png",
        status="CONNECTED",
    )
    return profile


class LeaderboardTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.campaign = make_campaign(slug="arena")
        self.alice = _creator("alice", "alice@example.com")
        self.bob = _creator("bob", "bob@example.com")

    def _get(self, **params):
        return self.client.get(URL, params)

    def test_it_is_public(self):
        # No authentication: the whole point is that a stranger can check it.
        self.assertEqual(self._get().status_code, 200)

    def test_ranks_by_settled_earnings(self):
        _reward(self.alice, self.campaign, "2")
        _reward(self.bob, self.campaign, "5")

        entries = self._get(campaign="arena").json()["entries"]

        self.assertEqual([entry["username"] for entry in entries], ["bob", "alice"])
        self.assertEqual(entries[0]["rank"], 1)
        self.assertEqual(Decimal(entries[0]["earned"]), Decimal("5"))

    def test_unsettled_rewards_are_not_published(self):
        # PENDING and VERIFIED are proposals staff may still reverse. Publishing
        # a figure we might have to take back is worse than publishing nothing.
        _reward(self.alice, self.campaign, "3", status=RewardStatus.PENDING)
        _reward(self.bob, self.campaign, "1", status=RewardStatus.VERIFIED)

        body = self._get(campaign="arena").json()

        self.assertEqual(body["entries"], [])
        self.assertEqual(Decimal(body["totals"]["paid"]), Decimal("0"))

    def test_a_creator_can_hide_their_figure_and_keep_their_rank(self):
        _reward(self.alice, self.campaign, "5")
        _reward(self.bob, self.campaign, "1")
        self.alice.show_earnings_publicly = False
        self.alice.save(update_fields=["show_earnings_publicly"])

        entries = self._get(campaign="arena").json()["entries"]
        hidden = next(entry for entry in entries if entry["username"] == "alice")

        self.assertTrue(hidden["hidden"])
        self.assertIsNone(hidden["earned"])
        self.assertIsNone(hidden["share"])
        self.assertEqual(hidden["rank"], 1)

    def test_no_address_like_string_is_ever_exposed(self):
        # A payout being public is the point; an address to attack is not.
        _reward(self.alice, self.campaign, "1")
        body = self._get(campaign="arena").content.decode()
        self.assertNotIn("0x", body)

    def test_totals_and_share(self):
        _reward(self.alice, self.campaign, "3")
        _reward(self.bob, self.campaign, "1")

        body = self._get(campaign="arena").json()

        self.assertEqual(Decimal(body["totals"]["paid"]), Decimal("4"))
        self.assertEqual(body["totals"]["creators"], 2)
        self.assertAlmostEqual(sum(e["share"] for e in body["entries"]), 1.0, places=6)

    def test_deltas_and_sparkline_series(self):
        _reward(self.alice, self.campaign, "2", days_ago=1)
        _reward(self.alice, self.campaign, "1", days_ago=20)

        body = self._get(campaign="arena").json()
        entry = body["entries"][0]

        self.assertEqual(Decimal(entry["delta_7d"]), Decimal("2"))
        self.assertEqual(Decimal(entry["delta_30d"]), Decimal("3"))
        self.assertEqual(len(entry["series"]), body["series_days"])

    def test_defaults_to_the_campaign_that_has_paid(self):
        make_campaign(slug="quiet")
        _reward(self.alice, self.campaign, "1")

        self.assertEqual(self._get().json()["campaign"]["slug"], "arena")

    def test_an_empty_platform_returns_an_empty_board(self):
        body = self._get().json()

        self.assertEqual(body["entries"], [])
        self.assertEqual(body["totals"]["creators"], 0)

    def test_unknown_campaign_is_a_404(self):
        self.assertEqual(self._get(campaign="nope").status_code, 404)

    def test_paging_reports_absolute_ranks(self):
        for index in range(3):
            _reward(_creator(f"c{index}", f"c{index}@example.com"), self.campaign, str(index + 1))

        body = self._get(campaign="arena", limit=2, offset=1).json()

        self.assertEqual([entry["rank"] for entry in body["entries"]], [2, 3])


class EarningsVisibilityToggleTests(TestCase):
    """Public by default is only a choice if the way out works."""

    def test_earnings_are_public_by_default(self):
        _user, profile = make_user()
        self.assertTrue(profile.show_earnings_publicly)

    def test_creator_can_hide_their_earnings(self):
        user, profile = make_user()
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.patch(
            "/api/v1/me/seller/", {"show_earnings_publicly": False}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        self.assertFalse(profile.show_earnings_publicly)

    def test_hiding_takes_effect_on_the_board(self):
        user, profile = make_user(email="hider@example.com", username="hider")
        SocialAccount.objects.create(
            seller=profile,
            platform=SocialPlatform.X,
            provider_user_id="hider",
            username="hider",
            status="CONNECTED",
        )
        campaign = make_campaign(slug="hide-me")
        _reward(profile, campaign, "4")

        client = APIClient()
        client.force_authenticate(user=user)
        client.patch("/api/v1/me/seller/", {"show_earnings_publicly": False}, format="json")

        entry = APIClient().get(URL, {"campaign": "hide-me"}).json()["entries"][0]
        self.assertTrue(entry["hidden"])
        self.assertIsNone(entry["earned"])


class CreatorCardTests(TestCase):
    """The shareable card: proof that a payout happened, for one person.

    It reports the same facts as the board and obeys the same opt-out, so a
    creator who hid their earnings still has something worth sharing - their
    standing - without their income on it.
    """

    def setUp(self):
        self.client = APIClient()
        self.campaign = make_campaign(slug="card-campaign")
        self.alice = _creator("alice", "alice@example.com")
        self.bob = _creator("bob", "bob@example.com")

    def _card(self, code):
        return self.client.get(f"/api/v1/card/{code}/")

    def test_it_is_public_and_reports_settled_earnings(self):
        _reward(self.alice, self.campaign, "3")
        _reward(self.bob, self.campaign, "5")

        response = self._card(self.alice.seller_code)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(Decimal(body["paid"]), Decimal("3"))
        self.assertEqual(body["username"], "alice")
        self.assertEqual(body["rewards"], 1)

    def test_it_reports_rank_within_the_best_campaign(self):
        _reward(self.alice, self.campaign, "3")
        _reward(self.bob, self.campaign, "5")

        body = self._card(self.alice.seller_code).json()

        self.assertEqual(body["best_campaign"]["rank"], 2)
        self.assertEqual(body["best_campaign"]["entrants"], 2)

    def test_hidden_earnings_keep_the_rank_and_drop_the_figures(self):
        _reward(self.alice, self.campaign, "3")
        self.alice.show_earnings_publicly = False
        self.alice.save(update_fields=["show_earnings_publicly"])

        body = self._card(self.alice.seller_code).json()

        self.assertTrue(body["hidden"])
        self.assertIsNone(body["paid"])
        self.assertEqual(body["best_campaign"]["rank"], 1)
        self.assertEqual(body["series"], [])

    def test_unsettled_rewards_do_not_appear(self):
        _reward(self.alice, self.campaign, "3", status=RewardStatus.PENDING)

        body = self._card(self.alice.seller_code).json()

        self.assertEqual(Decimal(body["paid"]), Decimal("0"))
        self.assertEqual(body["rewards"], 0)

    def test_unknown_creator_is_a_404(self):
        self.assertEqual(self._card("SELLER-NOPE").status_code, 404)

    def test_no_address_like_string_is_exposed(self):
        _reward(self.alice, self.campaign, "1")
        self.assertNotIn("0x", self._card(self.alice.seller_code).content.decode())


class DemoLabellingTests(TestCase):
    """Seeded data must be impossible to mistake for a real payout.

    The board's entire purpose is proving the platform pays, so a demo row on it
    is the most dangerous data in the system. These tests pin the three things
    that keep it honest: it is flagged, it says so on the page, and it can be
    removed in one command.
    """

    def _seed(self, creators=3, rewards_each=2):
        call_command("seed_arena_demo", confirm=True, creators=creators, rewards_each=rewards_each)

    def test_seeding_flags_everything_it_creates(self):
        self._seed()

        profiles = SellerProfile.objects.filter(is_demo=True)
        self.assertEqual(profiles.count(), 3)
        self.assertTrue(Reward.objects.filter(seller__in=profiles).exists())

    def test_seeding_is_idempotent(self):
        self._seed()
        before = Reward.objects.count()
        self._seed()
        self.assertEqual(Reward.objects.count(), before)

    def test_it_refuses_to_run_without_confirm(self):
        with self.assertRaises(CommandError):
            call_command("seed_arena_demo")

    def test_the_board_flags_demo_entries(self):
        self._seed(creators=2, rewards_each=1)

        body = APIClient().get(URL, {"campaign": "demo-arena"}).json()

        self.assertTrue(body["has_demo"])
        self.assertTrue(all(entry["demo"] for entry in body["entries"]))

    def test_a_real_creator_is_not_flagged(self):
        real = _creator("real", "real@example.com")
        _reward(real, make_campaign(slug="real-campaign"), "1")

        body = APIClient().get(URL, {"campaign": "real-campaign"}).json()

        self.assertFalse(body["has_demo"])
        self.assertFalse(body["entries"][0]["demo"])

    def test_seeded_accounts_cannot_be_signed_into(self):
        self._seed(creators=1, rewards_each=1)
        # NAMES[0] is Ana; the command also creates a non-staff `demo_seed`
        # account to own the demo campaign.
        for username in ("demo_ana", "demo_seed"):
            self.assertFalse(User.objects.get(username=username).has_usable_password())

    def test_purge_removes_everything_it_made(self):
        self._seed()
        call_command("seed_arena_demo", purge=True, confirm=True)

        self.assertFalse(SellerProfile.objects.filter(is_demo=True).exists())
        self.assertFalse(Reward.objects.exists())
        self.assertFalse(Campaign.objects.filter(slug="demo-arena").exists())
