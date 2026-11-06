"""Seed a demonstration arena, clearly labelled as demonstration data.

The leaderboard exists to prove the platform pays, which makes a fake row on it
the most dangerous kind of test data. So everything this creates is marked:
sellers carry `is_demo`, the campaign names itself as test data, and the API
flags every entry so the page can say so rather than leaving a visitor to guess.

    python manage.py seed_arena_demo --confirm
    python manage.py seed_arena_demo --purge --confirm

`--confirm` is required because this writes reward rows. `--purge` reverses it
exactly: the sellers it made, their payouts, and the demo campaign.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.campaigns.models import (
    Campaign,
    CampaignParticipation,
    CampaignStatus,
    RewardModel,
)
from apps.rewards.models import Reward, RewardStatus
from apps.sellers.models import SellerProfile
from apps.social.models import SocialAccount, SocialPlatform

CAMPAIGN_SLUG = "demo-arena"
NAMES = (
    "Ana", "Kwame", "Lena", "Tunde", "Mira", "Diego", "Sofia", "Ravi",
    "Nadia", "Emeka", "Yuki", "Pablo", "Ines", "Omar", "Zara", "Felix",
)
AMOUNTS = ("0.5", "1", "1", "1.5", "2", "2.5", "3")


class Command(BaseCommand):
    help = "Create (or remove) clearly-labelled demonstration creators and payouts."

    def add_arguments(self, parser):
        parser.add_argument("--creators", type=int, default=12)
        parser.add_argument("--rewards-each", type=int, default=4)
        parser.add_argument("--purge", action="store_true", help="Remove demo data.")
        parser.add_argument("--confirm", action="store_true", help="Required to write.")

    def handle(self, *args, **options):
        if not options["confirm"]:
            raise CommandError("This writes reward rows. Re-run with --confirm.")
        if options["purge"]:
            return self._purge()
        return self._seed(options["creators"], options["rewards_each"])

    def _seed(self, creators, rewards_each):
        now = timezone.now()
        # A campaign needs an owner. This uses a dedicated, non-staff account
        # rather than 'the first staff user', because a fresh install has none
        # and the command must not depend on one existing to run. Non-staff on
        # purpose: demo data should never carry privileges.
        owner, owner_created = User.objects.get_or_create(
            username="demo_seed", defaults={"email": "demo_seed@demo.invalid"}
        )
        if owner_created or owner.has_usable_password():
            owner.set_unusable_password()
            owner.save(update_fields=["password"])
        campaign, _ = Campaign.objects.get_or_create(
            slug=CAMPAIGN_SLUG,
            defaults={
                "name": "Demo arena (test data)",
                "project_name": "bagworkRH demo",
                "description": (
                    "Demonstration payouts, not real earnings. Labelled as test data "
                    "everywhere they appear."
                ),
                "token_symbol": "USDG",
                "chain_id": 46630,
                "budget": Decimal("500"),
                "remaining_budget": Decimal("500"),
                "reward_model": RewardModel.FIXED,
                "reward_rate": Decimal("1"),
                "start_at": now - timedelta(days=45),
                "end_at": now + timedelta(days=45),
                "status": CampaignStatus.ACTIVE,
                "created_by": owner,
            },
        )

        # Deterministic: a demo that looks different every time is harder to talk
        # over, and this is only ever presentation.
        rng = random.Random(20261030)
        created = 0
        for index in range(creators):
            name = NAMES[index % len(NAMES)]
            # The login name is internal and stays unmistakably marked, so it can
            # never be mistaken for a real account in the database. The handle a
            # visitor reads is a plain one: the demonstration flag is carried by
            # `is_demo`, the tile chip and the page banner, so the name does not
            # have to carry it too.
            login = f"demo_{name.lower()}"
            handle = name.lower()
            user, user_created = User.objects.get_or_create(
                username=login, defaults={"email": f"{login}@demo.invalid"}
            )
            if user_created or user.has_usable_password():
                # No password: these accounts must never be sign-in-able.
                user.set_unusable_password()
                user.save(update_fields=["password"])

            profile, _ = SellerProfile.objects.get_or_create(
                user=user, defaults={"display_name": name}
            )
            if not profile.is_demo:
                profile.is_demo = True
                profile.save(update_fields=["is_demo"])

            SocialAccount.objects.get_or_create(
                seller=profile,
                platform=SocialPlatform.X,
                provider_user_id=login,
                defaults={
                    "username": handle,
                    "status": "CONNECTED",
                    # These accounts stand in for working creators, and only a
                    # verified account's posts are tracked at all — a demo board
                    # staffed by creators who could not earn would misrepresent
                    # the product. The demonstration labelling is carried by
                    # `is_demo` and the API, exactly as it is for names.
                    "verified_type": "blue",
                    "verification_checked_at": timezone.now(),
                },
            )
            CampaignParticipation.objects.get_or_create(
                campaign=campaign, seller=profile, defaults={"status": "ACTIVE"}
            )

            existing = Reward.objects.filter(seller=profile, campaign=campaign).count()
            for _slot in range(max(0, rewards_each - existing)):
                amount = Decimal(rng.choice(AMOUNTS))
                reward = Reward.objects.create(
                    seller=profile,
                    campaign=campaign,
                    amount=amount,
                    gross_amount=amount,
                    token_symbol="USDG",
                    chain_id=46630,
                    status=RewardStatus.APPROVED,
                    explanation="Demonstration payout (test data).",
                )
                # Spread across the window so sparklines and deltas have shape.
                when = now - timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 20))
                Reward.objects.filter(pk=reward.pk).update(approved_at=when, created_at=when)
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"seeded {creators} demo creators and {created} demo rewards "
                f"into {CAMPAIGN_SLUG} (all flagged is_demo)"
            )
        )

    def _purge(self):
        profiles = SellerProfile.objects.filter(is_demo=True)
        users = User.objects.filter(id__in=list(profiles.values_list("user_id", flat=True)))
        campaign = Campaign.objects.filter(slug=CAMPAIGN_SLUG).first()

        with transaction.atomic():
            # Rewards PROTECT their seller and campaign, so they go first.
            Reward.objects.filter(seller__in=profiles).delete()
            CampaignParticipation.objects.filter(seller__in=profiles).delete()
            SocialAccount.objects.filter(seller__in=profiles).delete()
            profiles.delete()
            users.delete()
            if campaign:
                campaign.delete()
            # Only after the campaign is gone: created_by protects its owner.
            User.objects.filter(username="demo_seed").delete()

        self.stdout.write(
            self.style.SUCCESS("removed demo creators, their payouts and the demo campaign")
        )
