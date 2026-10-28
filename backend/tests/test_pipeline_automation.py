"""The pipeline advances without a human (Spec 03).

Discovery, verification and reward calculation all existed as tasks, but only
discovery was ever dispatched: nothing called `run_verification_on_post`, and
`calculate_pending_rewards` was in no beat schedule. So a creator's post was
found and then sat in DISCOVERED forever, and the product's central promise -
post and get paid with no manual step - was not actually true. These tests pin
the wiring, and that it stays cheap enough to run on every poll.
"""
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.rewards.models import Reward, RewardStatus
from apps.social.models import (
    PostVerificationStatus,
    SocialAccount,
    SocialPlatform,
    SocialPost,
)
from apps.social.providers.mock import MockSocialProvider
from apps.social.services import store_credentials
from apps.social.tasks import (
    calculate_pending_rewards,
    discover_posts_for_account,
    run_verification_on_post,
)

from .helpers import make_campaign, make_user


def _post(post_id, **extra):
    """A provider payload for a post published inside the campaign window."""
    return {
        "post_id": post_id,
        "text": "original #ad",
        "created_at": timezone.now() - timedelta(hours=1),
        **extra,
    }


class PipelineAutomationTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_user()
        self.campaign = make_campaign(slug="automation")
        self.account = SocialAccount.objects.create(
            seller=self.profile,
            platform=SocialPlatform.X,
            provider_user_id="42",
            username="alice",
            status="CONNECTED",
        )
        store_credentials(self.account, access_token="tok", refresh_token="ref")

    def _discover(self, found, *, stub_queue=True):
        """Run discovery, stubbing the queued verification unless a test wants it.

        A unit test has no broker, and `delay()` would sit there trying to reach
        one, so the dispatch is stubbed by default.
        """
        provider = MockSocialProvider(
            self.user, platform=SocialPlatform.X, discovered_posts=found
        )
        if stub_queue:
            with (
                mock.patch("apps.social.providers.get_provider", return_value=provider),
                mock.patch("apps.social.tasks.run_verification_on_post"),
            ):
                return self._run_task()
        with mock.patch("apps.social.providers.get_provider", return_value=provider):
            return self._run_task()

    def _run_task(self):
        return discover_posts_for_account.apply(
            args=[self.account.pk, self.campaign.pk]
        ).get()

    def test_every_new_post_is_queued_for_verification(self):
        with mock.patch("apps.social.tasks.run_verification_on_post") as queued:
            self._discover([_post("901"), _post("902")], stub_queue=False)

        queued_ids = sorted(call.args[0] for call in queued.delay.call_args_list)
        stored_ids = sorted(SocialPost.objects.values_list("pk", flat=True))
        self.assertEqual(queued_ids, stored_ids)
        self.assertEqual(len(queued_ids), 2)

    def test_a_post_already_stored_is_not_queued_again(self):
        found = [_post("903")]
        with mock.patch("apps.social.tasks.run_verification_on_post") as queued:
            self._discover(found, stub_queue=False)
            self._discover(found, stub_queue=False)

        # Polling repeats by design; only the first sighting may queue work.
        self.assertEqual(queued.delay.call_count, 1)

    def test_verifying_a_discovered_post_costs_no_provider_call(self):
        # Originality on a discovered post is already a provider fact, so the
        # refresh that a self-reported post needs must not happen here. This is
        # what makes queueing one task per discovered post affordable.
        self._discover([_post("904")])
        post = SocialPost.objects.get(external_post_id="904")
        with mock.patch("apps.social.tasks.refresh_post_facts") as refreshed:
            result = run_verification_on_post(post.pk)
        self.assertFalse(refreshed.called)
        self.assertEqual(result["status"], PostVerificationStatus.VERIFIED)

    def test_discovery_to_reward_needs_no_human_step(self):
        # The whole automatic chain: poll, verify, reward. Approval is the only
        # step left, and that is deliberate - it is what moves money.
        self._discover([_post("905")])
        post = SocialPost.objects.get(external_post_id="905")

        run_verification_on_post(post.pk)
        calculate_pending_rewards()

        reward = Reward.objects.get(post=post)
        self.assertEqual(reward.status, RewardStatus.PENDING)
        self.assertEqual(reward.amount, self.campaign.reward_rate)

    def test_the_reward_sweep_does_not_pay_twice(self):
        self._discover([_post("906")])
        post = SocialPost.objects.get(external_post_id="906")
        run_verification_on_post(post.pk)

        calculate_pending_rewards()
        calculate_pending_rewards()

        self.assertEqual(Reward.objects.filter(post=post).count(), 1)

    def test_a_post_outside_the_window_is_never_paid(self):
        # Queueing verification must not turn into paying for anything the
        # campaign window excludes.
        self._discover([_post("907", created_at=timezone.now() - timedelta(days=90))])
        post = SocialPost.objects.get(external_post_id="907")
        run_verification_on_post(post.pk)
        calculate_pending_rewards()
        self.assertFalse(Reward.objects.filter(post=post).exists())

    def test_reward_sweep_is_scheduled(self):
        entry = settings.CELERY_BEAT_SCHEDULE["calculate-pending-rewards"]
        self.assertEqual(entry["task"], "apps.social.tasks.calculate_pending_rewards")
