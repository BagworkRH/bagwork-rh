"""Shared test helpers for the platform test suite."""
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from eth_account import Account
from hexbytes import HexBytes
from web3 import Web3
from web3.datastructures import AttributeDict
from web3.types import HexStr

from apps.blockchain import signing
from apps.blockchain.models import TokenConfig
from apps.campaigns.models import Campaign, CampaignStatus, RewardModel
from apps.sellers.models import SellerProfile
from apps.social.models import (
    OriginalityEvidence,
    PostVerificationStatus,
    SocialPlatform,
    SocialPost,
)
from apps.wallets.models import Wallet

User = get_user_model()

TREASURY = "0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC"
TRANSFER_TOPIC_FULL = Web3.keccak(text="Transfer(address,address,uint256)").hex()


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
    token_symbol="TST",
    chain_id=11155111,
    funding_brand=None,
):
    """Create a campaign owned by a staff user."""
    now = timezone.now()
    admin = make_staff()
    campaign = Campaign.objects.create(
        name=name,
        slug=slug,
        description="desc",
        project_name="Project",
        token_symbol=token_symbol,
        chain_id=chain_id,
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
        funding_brand=funding_brand,
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


def make_post(profile, campaign, external_id, text="#", **kwargs):
    """Create a SocialPost with test-friendly defaults.

    Defaults to provider-confirmed originality: since a post only earns when
    the platform has confirmed it, any test that expects a payout must supply
    that evidence rather than inherit an assumption.
    """
    defaults = {
        "account": None,
        "platform": SocialPlatform.X,
        "external_post_id": external_id,
        "seller": profile,
        "campaign": campaign,
        "post_url": f"https://x.com/status/{external_id}",
        "text_snapshot": text,
        "published_at": timezone.now(),
        "originality_evidence": OriginalityEvidence.PROVIDER_CONFIRMED,
    }
    defaults.update(kwargs)
    return SocialPost.objects.create(**defaults)


def make_verified_post(  # noqa: PLR0913 - test helper with sensible defaults
    profile,
    campaign,
    external_id="123456789",
    text="#",
    *,
    platform=SocialPlatform.X,
    originality_evidence=OriginalityEvidence.PROVIDER_CONFIRMED,
):
    """Create a post already in VERIFIED state.

    Defaults to provider-confirmed originality, since a VERIFIED post with an
    unconfirmed originality claim is no longer payable and most reward tests
    are about the money path.
    """
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
        originality_evidence=originality_evidence,
    )
    return post


def transfer_log(token_address, sender, recipient, amount_units):
    """One real ERC-20 Transfer log, encoded the way a node returns it.

    Built by encoding through Web3 rather than by pasting hex, so a test
    fixture cannot drift from the event the verifier actually parses.
    """
    sender_topic = HexBytes(HexStr("0x" + "0" * 24 + sender[2:].lower()))
    recipient_topic = HexBytes(HexStr("0x" + "0" * 24 + recipient[2:].lower()))
    return {
        "address": Web3.to_checksum_address(token_address),
        "topics": (HexBytes(HexStr(TRANSFER_TOPIC_FULL)), sender_topic, recipient_topic),
        "data": HexBytes(amount_units),
    }


def fake_web3(
    *,
    chain_id=46630,
    head=100,
    receipt=None,
    receipt_error=None,
):
    """A stand-in node that returns a caller-controlled receipt.

    This fakes the *transport*, not the verification. `verify_deposit` still
    parses the log, matches the token contract, compares the recipient, reads
    decimals and counts confirmations, so a test that passes here proves the
    real code accepts a real-looking transfer — and a test that expects a
    rejection proves the real code refuses it.
    """
    eth = SimpleNamespace(
        chain_id=chain_id,
        block_number=head,
        get_transaction_receipt=(
            (lambda _h: (_ for _ in ()).throw(receipt_error)) if receipt_error else (lambda _h: receipt)
        ),
    )
    return SimpleNamespace(eth=eth)


def fake_receipt(*, block_number=90, status=1, logs=()):
    """A receipt shaped like the one web3 actually returns.

    `AttributeDict` rather than a bare namespace because a real receipt is one:
    the verifier reads `receipt.get("logs", [])` and `receipt.blockNumber`, and
    a fake supporting only the second would let a mismatch between the fixture
    and the live interface pass unnoticed.
    """
    return AttributeDict({"status": status, "blockNumber": block_number, "logs": list(logs)})


def funding_settings(confirmations=3, treasury=TREASURY):
    """Settings with a treasury and an RPC, so funding can be verified at all.

    `FUNDING_TREASURY_ADDRESS` is deliberately a real-looking address rather
    than a placeholder: the verifier checksums it and compares it against the
    transfer recipient, and "0x000...0" would make several rejection paths
    unreachable in tests.
    """
    return override_settings(
        FUNDING_TREASURY_ADDRESS=treasury,
        FUNDING_CONFIRMATIONS=confirmations,
        RPC_URL="http://127.0.0.1:8545",
        CONTRACT_ADDRESS="0x00000000000000000000000000000000000000CC",
        CHAIN_ID=46630,
    )


@contextmanager
def chain_showing(  # noqa: PLR0913 - one keyword per way a deposit can fail
    *,
    amount_units=100 * 10**18,
    token_address,
    recipient=TREASURY,
    sender="0x1234567890123456789012345678901234567890",
    chain_id=46630,
    head=100,
    block_number=90,
    status=1,
    logs=None,
    no_receipt=False,
    confirmations=3,
    treasury=TREASURY,
    node=True,
):
    """Present a specific chain to the deposit verifier.

    The *node* is faked; the *verification* is not. `verify_deposit` still
    parses the log, matches the emitting contract, compares the recipient, reads
    decimals from the allowlist and counts confirmations against the head. So a
    test that credits money here is evidence the real code accepts a real
    transfer, and a test that expects a refusal is evidence it catches the
    attempt.

    Each keyword is one way a deposit can fail to verify, which is why there are
    so many of them: they are the cases, not configuration.
    """
    if logs is None and not no_receipt:
        logs = [transfer_log(token_address, sender, recipient, amount_units)]
    receipt = None
    if not no_receipt:
        receipt = fake_receipt(block_number=block_number, status=status, logs=logs or [])
    w3 = fake_web3(chain_id=chain_id, head=head, receipt=receipt)
    target = w3 if node else None
    with funding_settings(confirmations=confirmations, treasury=treasury):
        with mock.patch("apps.blockchain.deposits.get_web3", return_value=target):
            yield
