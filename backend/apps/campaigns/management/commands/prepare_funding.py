"""Rehearse the brand funding rail end to end (Stage 6, dev/testnet only).

Records a brand deposit from an on-chain transfer, confirms it (which reads the
receipt via `verify_deposit` — recording a deposit is not crediting it), and —
with `--launch` — creates and launches a brand-funded campaign, so the funding
gate is exercised rather than assumed.

    python manage.py prepare_funding --company "Acme" --amount 5 \
        --tx-hash 0x... --slug acme-launch --launch
"""
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal
from typing import NamedTuple

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import User
from apps.blockchain import fees
from apps.blockchain.models import TokenConfig
from apps.campaigns.funding import (
    confirm_funding,
    confirmed_funded_balance,
    get_or_create_brand,
    quote_campaign_cost,
    record_funding,
)
from apps.campaigns.models import Campaign, CampaignStatus, RewardModel
from apps.campaigns.services import create_campaign, set_campaign_status
from apps.rewards.exceptions import RewardEngineError

BPS_DENOMINATOR = Decimal(10000)


class _CampaignSpec(NamedTuple):
    """The rehearsal-campaign fields derived from the brand's confirmed balance."""

    symbol: str
    chain_id: int
    budget: Decimal


class Command(BaseCommand):
    help = "Record + confirm a brand deposit; optionally launch a funded campaign."

    def add_arguments(self, parser):
        parser.add_argument("--company", required=True)
        parser.add_argument("--amount", required=True, help="Deposit amount in whole tokens.")
        parser.add_argument("--tx-hash", required=True, help="The on-chain transfer hash.")
        parser.add_argument("--slug", default=None, help="Create a brand-funded campaign with this slug.")
        parser.add_argument("--launch", action="store_true", help="Launch it (exercises the funding gate).")
        parser.add_argument("--chain-id", type=int, default=None)
        parser.add_argument("--symbol", default=None)

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("prepare_funding is a development rehearsal tool; DEBUG is off.")

        chain_id = options["chain_id"] or int(settings.CHAIN_ID)
        symbol = options["symbol"] or settings.FUNDING_TOKEN_SYMBOL
        amount = Decimal(str(options["amount"]))

        user, _ = User.objects.get_or_create(
            username="rehearsal_brand", defaults={"email": "rehearsal_brand@example.com"}
        )
        brand = get_or_create_brand(user, company_name=options["company"], actor=user)

        funding = record_funding(
            brand,
            amount=amount,
            chain_id=chain_id,
            tx_hash=options["tx_hash"],
            token_symbol=symbol,
            actor=user,
        )
        self.stdout.write(
            f"Recorded deposit {funding.pk} ({amount} {symbol}) as {funding.status} — not yet credited."
        )

        confirmed = confirm_funding(funding, actor=user)
        balance = confirmed_funded_balance(brand)
        self.stdout.write(
            self.style.SUCCESS(
                f"Confirmed on-chain: sender {confirmed.verified_sender}, block "
                f"{confirmed.verified_block}, amount {confirmed.verified_amount}. "
                f"Brand balance: {balance} {symbol}."
            )
        )

        if not options["slug"]:
            return

        decimals = self._decimals(symbol, chain_id)
        budget = (balance * BPS_DENOMINATOR / (BPS_DENOMINATOR + fees.fee_bps())).quantize(
            Decimal(1).scaleb(-decimals), rounding=ROUND_DOWN
        )
        spec = _CampaignSpec(symbol=symbol, chain_id=chain_id, budget=budget)
        campaign = self._ensure_campaign(user, brand, options["slug"], spec)
        quote = quote_campaign_cost(brand, payout_total=campaign.budget, decimals=decimals)
        self.stdout.write(
            f"Campaign '{campaign.slug}' budget {campaign.budget} {symbol}; "
            f"needs {quote['total_required']} (fee {quote['platform_fee']}), "
            f"funded {quote['already_funded']}, sufficient={quote['sufficient']}."
        )

        if not options["launch"]:
            return

        try:
            campaign = set_campaign_status(campaign, CampaignStatus.ACTIVE, actor=user)
        except RewardEngineError as exc:
            self.stderr.write(self.style.ERROR(f"Launch refused by the funding gate: {exc}"))
            raise CommandError("Campaign launch failed.") from exc
        self.stdout.write(
            self.style.SUCCESS(f"Campaign '{campaign.slug}' launched: status {campaign.status}.")
        )

    def _decimals(self, symbol, chain_id) -> int:
        token = TokenConfig.objects.filter(symbol__iexact=symbol, chain_id=chain_id).first()
        return token.decimals if token else settings.DEFAULT_TOKEN_DECIMALS

    def _ensure_campaign(self, user, brand, slug, spec: _CampaignSpec) -> Campaign:
        existing = Campaign.objects.filter(slug=slug).first()
        if existing is not None:
            return existing

        now = timezone.now()
        return create_campaign(
            created_by=user,
            actor=user,
            name=f"{brand.company_name} campaign",
            slug=slug,
            project_name=brand.company_name,
            description="Stage 6 funding rehearsal.",
            token_symbol=spec.symbol,
            chain_id=spec.chain_id,
            budget=spec.budget,
            reward_model=RewardModel.FIXED,
            reward_rate=Decimal(1),
            start_at=now - timedelta(days=1),
            end_at=now + timedelta(days=30),
        )
