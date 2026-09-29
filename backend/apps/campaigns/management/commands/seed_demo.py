"""Seed realistic local demo data.

The landing page renders live figures from `GET /api/v1/campaigns/stats/`.
This command populates a believable local dataset so those figures are real
numbers from a real database rather than placeholders.

    python manage.py seed_demo            # 6 sellers, 4 campaigns, 40 posts
    python manage.py seed_demo --flush    # wipe and rebuild

Refuses to run when DEBUG is off: this writes unreviewed data and must never
reach a shared environment.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.campaigns.models import Campaign, CampaignStatus, RewardModel
from apps.rewards.models import Reward, RewardStatus
from apps.sellers.models import SellerProfile
from apps.social.models import PostVerificationStatus, SocialPost

UserModel = get_user_model()

CAMPAIGNS = [
    ("Robinhood Chain Launch", "rh-launch",
     "Promote the Robinhood Chain launch on X.", "15000", "4.50"),
    ("Arbitrum Developer Week", "arb-dev-week",
     "Share your Arbitrum build in public.", "8000", "3.00"),
    ("Wallet Connect Sprint", "wallet-sprint",
     "Show your wallet onboarding flow.", "5000", "2.50"),
    ("Open Source Promo", "oss-promo",
     "Highlight a public repo you maintain.", "3000", "1.80"),
]

SELLER_NAMES = ["ada", "grace", "linus", "margaret", "alan", "barbara"]

# Weighted toward VERIFIED so the verification rate looks plausible.
POST_STATES = [
    PostVerificationStatus.VERIFIED,
    PostVerificationStatus.VERIFIED,
    PostVerificationStatus.VERIFIED,
    PostVerificationStatus.REWARD_CALCULATED,
    PostVerificationStatus.APPROVED,
    PostVerificationStatus.DISCOVERED,
]
REWARDED_STATES = {
    PostVerificationStatus.VERIFIED,
    PostVerificationStatus.REWARD_CALCULATED,
    PostVerificationStatus.APPROVED,
}

# Share of rewards already claimed, so the demo shows both paid and outstanding.
CLAIMED_SHARE = 0.55


class Command(BaseCommand):
    help = "Populate the local database with demo sellers, campaigns, posts and rewards."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing sellers, campaigns, posts and rewards first.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_demo is a development-only command and refuses to run "
                "with DEBUG=False."
            )

        if options["flush"]:
            Reward.objects.all().delete()
            SocialPost.objects.all().delete()
            Campaign.objects.all().delete()
            SellerProfile.objects.all().delete()
            UserModel.objects.filter(is_superuser=False).delete()
            self.stdout.write(self.style.WARNING("Flushed existing demo data."))

        staff, _ = UserModel.objects.get_or_create(
            email="demo-owner@example.com",
            defaults={"username": "demo_owner", "is_staff": True, "is_superuser": True},
        )
        staff.set_password("demo-owner-pass-123")
        staff.save()
        SellerProfile.objects.get_or_create(user=staff)

        campaigns = []
        for name, slug, description, budget, rate in CAMPAIGNS:
            campaign, _ = Campaign.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "project_name": "bagworkRH",
                    "description": description,
                    "token_symbol": "RWD",
                    "chain_id": 46630,
                    "budget": Decimal(budget),
                    "remaining_budget": Decimal(budget),
                    "reward_rate": Decimal(rate),
                    "reward_model": RewardModel.FIXED,
                    # Rewards are paid for original, disclosed posts. The demo
                    # campaign requires a disclosure so seeded posts show a
                    # mix of disclosed and non-disclosed submissions.
                    "requirements_json": {"required_disclosure": ["#ad"]},
                    "created_by": staff,
                    "status": CampaignStatus.ACTIVE,
                    "start_at": timezone.now() - timedelta(days=7),
                    "end_at": timezone.now() + timedelta(days=21),
                },
            )
            campaigns.append(campaign)

        sellers = []
        for name in SELLER_NAMES:
            user, created = UserModel.objects.get_or_create(
                email=f"{name}@example.com", defaults={"username": name},
            )
            if created:
                user.set_password("demo-seller-pass-123")
                user.save()
            sellers.append(SellerProfile.objects.get_or_create(user=user)[0])

        rng = random.Random(1337)  # deterministic, so reruns look identical
        posts_created = rewards_created = 0

        for i in range(40):
            seller = rng.choice(sellers)
            campaign = rng.choice(campaigns)
            state = rng.choice(POST_STATES)
            post, created = SocialPost.objects.get_or_create(
                external_post_id=f"demo-{i:04d}",
                defaults={
                    "seller": seller,
                    "campaign": campaign,
                    "post_url": f"https://x.com/{seller.user.username}/status/{900000 + i}",
                    "text_snapshot": f"Demo qualifying post #{i} for {campaign.name}.",
                    "published_at": timezone.now() - timedelta(hours=rng.randint(1, 240)),
                    "verification_status": state,
                },
            )
            if not created:
                continue
            posts_created += 1

            if state in REWARDED_STATES:
                amount = Decimal(str(rng.randint(20, 400)))
                Reward.objects.get_or_create(
                    post=post,
                    defaults={
                        "seller": seller,
                        "campaign": campaign,
                        "amount": amount,
                        "gross_amount": amount,
                        "token_symbol": "RWD",
                        "chain_id": 46630,
                        "status": (
                            RewardStatus.CLAIMED
                            if rng.random() < CLAIMED_SHARE
                            else RewardStatus.AVAILABLE
                        ),
                    },
                )
                rewards_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(campaigns)} campaigns, {len(sellers)} sellers, "
                f"{posts_created} posts, {rewards_created} rewards."
            )
        )
        self.stdout.write(
            "Demo owner login: demo-owner@example.com / demo-owner-pass-123"
        )
        self.stdout.write(
            "Seller logins: ada@example.com .. barbara@example.com / demo-seller-pass-123"
        )
        self.stdout.write("Landing page figures: /api/v1/campaigns/stats/")
