"""Shared test helpers for the platform test suite."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.campaigns.models import Campaign, CampaignStatus, RewardModel
from apps.sellers.models import SellerProfile
from apps.social.models import PostVerificationStatus, SocialPost

User = get_user_model()


def make_user(email="seller@example.com", username="seller", password="Testpass123!"):
    """Create and return a user with a seller profile."""
    user = User.objects.create_user(username=username, email=email, password=password)
    profile = SellerProfile.objects.create(user=user)
    return user, profile


def make_staff(email="admin@example.com", username="admin"):
    user = User.objects.create_user(
        username=username, email=email, password="Testpass123!", is_staff=True
    )
    return user


def make_campaign(  # noqa: PLR0913 - test helper with sensible defaults
    *,
    name="Test Campaign",
    slug="test-campaign",
    reward_model=RewardModel.FIXED,
    reward_rate=Decimal("5"),
    budget=Decimal("1000"),
    start_at=None,
    end_at=None,
    requirements_json=None,
    status=CampaignStatus.ACTIVE,
    maximum_reward_per_seller=Decimal("0"),
    maximum_rewards_per_seller=0,
):
    """Create a campaign owned by a staff user."""
    now = timezone.now()
    admin = make_staff()
    campaign = Campaign.objects.create(
        name=name,
        slug=slug,
        description="desc",
        project_name="Project",
        token_symbol="TST",
        chain_id=11155111,
        budget=budget,
        remaining_budget=budget,
        reward_model=reward_model,
        reward_rate=reward_rate,
        maximum_reward_per_seller=maximum_reward_per_seller,
        maximum_rewards_per_seller=maximum_rewards_per_seller,
        start_at=start_at or (now - timedelta(days=1)),
        end_at=end_at or (now + timedelta(days=30)),
        status=status,
        requirements_json=requirements_json or {},
        created_by=admin,
    )
    return campaign


def make_verified_post(profile, campaign, external_id="123456789", text="#"):
    """Create a post already in VERIFIED state."""
    post = SocialPost.objects.create(
        x_account=None,
        external_post_id=external_id,
        seller=profile,
        campaign=campaign,
        post_url=f"https://x.com/status/{external_id}",
        text_snapshot=text,
        published_at=timezone.now(),
        verification_status=PostVerificationStatus.VERIFIED,
    )
    return post