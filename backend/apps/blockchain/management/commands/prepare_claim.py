"""Prepare a claim for an on-chain rehearsal (Stage 6, dev/testnet only).

Sets up (idempotently) a demo seller with a verified wallet, a staff-funded
campaign paying in the allowlisted token, and an AVAILABLE reward; then creates
a claim and writes the signed EIP-712 authorization to a JSON file.

It deliberately does NOT send a transaction: the wallet owns the key that
submits a claim, exactly as in production. Use scripts/submit-claim.ts (in the
contracts package) to broadcast the file this command writes.

    python manage.py prepare_claim \
        --seller-address 0x... --amount 1 --out claim-authorization.json
"""
import json
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import User
from apps.blockchain.services import get_claim_authorization_payload
from apps.campaigns.models import Campaign, CampaignStatus, RewardModel
from apps.rewards.models import Reward, RewardStatus
from apps.sellers.models import SellerProfile
from apps.wallets.models import Wallet
from apps.wallets.services import create_claim


class Command(BaseCommand):
    help = "Create a claim fixture and write its signed authorization to a file."

    def add_arguments(self, parser):
        parser.add_argument("--seller-address", required=True, help="EVM address that claims.")
        parser.add_argument("--amount", default="1", help="Reward amount in whole tokens.")
        parser.add_argument("--out", required=True, help="Where to write the authorization JSON.")
        parser.add_argument("--symbol", default=None, help="Payout token (default: funding token).")
        parser.add_argument("--chain-id", type=int, default=None, help="Chain id (default: CHAIN_ID).")
        parser.add_argument("--campaign-slug", default="rehearsal-claim")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("prepare_claim is a development rehearsal tool; DEBUG is off.")

        chain_id = options["chain_id"] or int(settings.CHAIN_ID)
        symbol = options["symbol"] or settings.FUNDING_TOKEN_SYMBOL
        amount = Decimal(str(options["amount"]))

        user, _ = User.objects.get_or_create(
            username="rehearsal_seller", defaults={"email": "rehearsal_seller@example.com"}
        )
        seller, _ = SellerProfile.objects.get_or_create(
            user=user, defaults={"display_name": "Rehearsal Seller", "status": SellerProfile.Status.ACTIVE}
        )
        wallet, _ = Wallet.objects.get_or_create(
            seller=seller,
            address=options["seller_address"],
            chain_id=chain_id,
            defaults={"verified": True},
        )
        if not wallet.verified:
            wallet.verified = True
            wallet.save(update_fields=["verified"])

        # Staff-funded (funding_brand=None) so the funding gate is skipped: this
        # rehearses the claim mechanics, not the brand-deposit flow.
        now = timezone.now()
        campaign, _ = Campaign.objects.get_or_create(
            slug=options["campaign_slug"],
            defaults={
                "name": "Rehearsal Claim Campaign",
                "project_name": "Rehearsal",
                "description": "Stage 6 claim rehearsal.",
                "token_symbol": symbol,
                "chain_id": chain_id,
                "budget": amount * 100,
                "remaining_budget": amount * 100,
                "reward_model": RewardModel.FIXED,
                "reward_rate": amount,
                "start_at": now - timedelta(days=1),
                "end_at": now + timedelta(days=30),
                "status": CampaignStatus.ACTIVE,
                "created_by": user,
            },
        )

        # A fresh reward each run: its id is the on-chain `rewardId`, and a new id
        # keeps the contract's replay guard from rejecting the claim.
        reward = Reward.objects.create(
            seller=seller,
            campaign=campaign,
            amount=amount,
            gross_amount=amount,
            token_symbol=symbol,
            chain_id=chain_id,
            status=RewardStatus.AVAILABLE,
            explanation="Stage 6 rehearsal reward.",
        )

        claim = create_claim(seller, wallet, reward, actor=user)
        payload = get_claim_authorization_payload(claim)

        with open(options["out"], "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

        self.stdout.write(
            self.style.SUCCESS(
                f"Claim {claim.pk} prepared: {payload['amount']} {payload['token_symbol']} "
                f"to {payload['wallet']} (rewardId {payload['reward_id']}).\n"
                f"Authorization written to {options['out']}."
            )
        )
