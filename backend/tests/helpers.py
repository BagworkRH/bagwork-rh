"""Shared test helpers for the platform test suite."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from eth_account import Account

from apps.blockchain import signing
from apps.blockchain.models import TokenConfig
from apps.campaigns.models import Campaign, CampaignStatus, RewardModel
from apps.sellers.models import SellerProfile
from apps.social.models import PostVerificationStatus, SocialPlatform, SocialPost
from apps.wallets.models import Wallet

User = get_user_model()


def make_user(email="seller@example.com", username="seller", password="Testpass123!"):
    """Create and return a user with a seller profile."""
    user = User.objects.create_user(username=username, email=email, password=password)
    profile = SellerProfile.objects.create(user=user)
    return user, profile


def make_staff(email="admin@example.com", username="admin"):
    """Create a staff user, reusing an existing one with the same email.

    Idempotent on email so helpers that each create their own admin
    (e.g. `make_campaign`) can be combined freely in one test.
    """
    existing = User.objects.filter(email=email).first()
    if existing is not None:
        return existing
    return User.objects.create_user(
        username=username, email=email, password="Testpass123!", is_staff=True
    )


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


def make_token_config(
    symbol="TST",
    chain_id=11155111,
    address="0x00000000000000000000000000000000000000AA",
    decimals=18,
):
    """Allowlist a reward token (Spec 04) so claims can be authorized.

    Idempotent: `symbol` and `address` are both unique, so tests can call this
    without coordinating with other helpers.
    """
    token, _ = TokenConfig.objects.get_or_create(
        symbol=symbol,
        defaults={
            "chain_id": chain_id,
            "address": address,
            "decimals": decimals,
            "enabled": True,
        },
    )
    return token


def claim_signer_key():
    """Deterministic test private key for the claim-authorization signer."""
    return "0x" + "11" * 32


def signer_address():
    return Account.from_key(claim_signer_key()).address


def signer_settings(contract_address="0x00000000000000000000000000000000000000BB"):
    """Settings override enabling the signed-claim flow in tests.

    RPC_URL stays empty on purpose: signing must work without a node, and the
    listener/reconciliation tasks must keep reporting "disabled".
    """
    return override_settings(
        CONTRACT_ADDRESS=contract_address,
        CLAIM_SIGNER=claim_signer_key(),
        RPC_URL="",
    )


# --- Ethers.js cross-check fixtures (Phase 6) ------------------------------ #
# Generated with the real JS stack (`ethers.Interface` / `TypedDataEncoder` /
# `Wallet.signTypedData`) in contracts/src/reward_token/_crosscheck.js. The
# Python signing + ABI code must reproduce these byte-for-byte, which proves the
# backend and the contract agree on the EIP-712 domain/struct and calldata.
CROSS_CHECK = {
    'chain_id': 11155111,
    'contract_address': '0x00000000000000000000000000000000000000BB',
    'token_address': '0x00000000000000000000000000000000000000AA',
    'wallet': '0x1111111111111111111111111111111111111111',
    'reward_id': 1,
    'amount_smallest_unit': 5000000000000000000,
    'nonce': 1,
    'deadline': 1893456000,
    'selector': '0xedc19c89',
    'domain_separator': '0x9bac57e0ef1e65cab89c9cc135c54dc5b5a6fe8adca352ae4848721a6cb0ee5a',
    'struct_hash': '0xc5522b7413d2712d519e432925a4d2ec67c65088278e7657ac0310e440277e65',
    'digest': '0x1bfd509bc7eea3f9e58cb4d9b1fa2c9b829bf8356ca4eba90c5c856536238b81',
    'signer_address': '0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A',
    'signature': (
        '0x00e01afd1b20a9e84c111907b1d8bd0d2cff49038be998143c1b3068ebda09'
        '7766c09f9376e89dd9048dc8c48791d230ea17e2cd0ce93cccb9129a56eb45f5'
        '061c'
    ),
    'calldata': (
        '0xedc19c89000000000000000000000000000000000000000000000000000000'
        '0000000001000000000000000000000000111111111111111111111111111111'
        '1111111111000000000000000000000000000000000000000000000000456391'
        '8244f40000000000000000000000000000000000000000000000000000000000'
        '0000000001000000000000000000000000000000000000000000000000000000'
        '0070dbd880000000000000000000000000000000000000000000000000000000'
        '00000000c0000000000000000000000000000000000000000000000000000000'
        '000000004100e01afd1b20a9e84c111907b1d8bd0d2cff49038be998143c1b30'
        '68ebda097766c09f9376e89dd9048dc8c48791d230ea17e2cd0ce93cccb9129a'
        '56eb45f5061c0000000000000000000000000000000000000000000000000000'
        '0000000000'
    ),
}


def cross_check_claim_digest():
    """The ethers-defined Claim struct for the cross-check fixture."""
    return signing.build_claim_digest(
        wallet=CROSS_CHECK["wallet"],
        reward_id=CROSS_CHECK["reward_id"],
        token_address=CROSS_CHECK["token_address"],
        amount=CROSS_CHECK["amount_smallest_unit"],
        nonce=CROSS_CHECK["nonce"],
        deadline=CROSS_CHECK["deadline"],
        chain_id=CROSS_CHECK["chain_id"],
        contract_address=CROSS_CHECK["contract_address"],
    )


def chain_settings(rpc_url="http://127.0.0.1:8545"):
    """Settings override with a contract + RPC configured.

    The RPC URL deliberately points at nothing: `get_web3()` returns None when
    the node is unreachable, so listener/reconciliation paths stay in their
    "disabled" branch while `chain_enabled()` reports configured.
    """
    return override_settings(
        CONTRACT_ADDRESS=CROSS_CHECK["contract_address"],
        RPC_URL=rpc_url,
        CHAIN_ID=CROSS_CHECK["chain_id"],
    )


def make_verified_wallet(
    profile,
    address="0x1111111111111111111111111111111111111111",
    chain_id=11155111,
    verified=True,
):
    """Create a wallet row for a seller (ownership verification bypassed).

    Idempotent on (seller, address, chain_id) so helpers can be combined freely.
    """
    wallet, _ = Wallet.objects.get_or_create(
        seller=profile,
        address=address.lower(),
        chain_id=chain_id,
        defaults={"verified": verified, "nonce": "" if verified else "abc123"},
    )
    return wallet


def make_verified_post(
    profile, campaign, external_id="123456789", text="#", platform=SocialPlatform.X
):
    """Create a post already in VERIFIED state."""
    post = SocialPost.objects.create(
        account=None,
        platform=platform,
        external_post_id=external_id,
        seller=profile,
        campaign=campaign,
        post_url=f"https://x.com/status/{external_id}",
        text_snapshot=text,
        published_at=timezone.now(),
        verification_status=PostVerificationStatus.VERIFIED,
    )
    return post