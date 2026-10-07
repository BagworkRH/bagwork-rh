"""Register (or update) a reward token in the allowlist (Spec 04 / Stage 6).

A campaign's payout token must be allowlisted for its chain before a campaign
paying in it can be created, and a claim's decimals are read from this row at
claim time. So an unregistered token is not a cosmetic gap: it refuses
campaigns and, if the decimals are wrong, scales every payout by a power of ten.
Until now the only ways to add one were the Django admin or a hand-written shell
snippet; this is the scripted, repeatable version.

    python manage.py register_token --symbol USDG --chain-id 46630 \
        --address 0x... --decimals 6

`symbol` is globally unique (one symbol maps to one chain, by model design), so
this upserts by symbol rather than creating duplicates.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.blockchain.models import TokenConfig

# An EIP-55 address is "0x" plus 20 bytes as hex: 2 + 40 = 42 chars.
ADDRESS_LENGTH = 42

# Decimals are an unsigned byte; 18 is the conventional ceiling (ETH's precision).
MAX_DECIMALS = 18


class Command(BaseCommand):
    help = "Allowlist a reward token for a chain (idempotent upsert by symbol)."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", required=True, help="Token symbol, e.g. USDG.")
        parser.add_argument(
            "--chain-id", type=int, required=True, dest="chain_id", help="Chain id, e.g. 46630."
        )
        parser.add_argument("--address", required=True, help="ERC-20 contract address (0x...).")
        parser.add_argument(
            "--decimals", type=int, required=True, help="Token decimals, e.g. 6 for USDG."
        )
        parser.add_argument("--min-claim", default=None, dest="min_claim", help="Optional min claim.")
        parser.add_argument("--max-claim", default=None, dest="max_claim", help="Optional max claim.")
        parser.add_argument(
            "--disable",
            action="store_true",
            help="Register the token but leave it disabled for claiming.",
        )

    def handle(self, *args, **options):
        symbol = options["symbol"].strip().upper()
        address = options["address"].strip()
        decimals = options["decimals"]
        chain_id = options["chain_id"]

        if not symbol:
            raise CommandError("--symbol is required.")
        if not (address.startswith("0x") and len(address) == ADDRESS_LENGTH):
            raise CommandError(
                f"--address must be a 20-byte hex address (0x + 40 hex): got {address!r}."
            )
        if decimals < 0 or decimals > MAX_DECIMALS:
            raise CommandError("--decimals must be between 0 and 18.")
        if chain_id <= 0:
            raise CommandError("--chain-id must be a positive integer.")

        # `address` is unique too. A second symbol pointing at the same contract
        # would make the allowlist ambiguous about which decimals apply.
        clash = TokenConfig.objects.filter(address=address).exclude(symbol=symbol).first()
        if clash:
            raise CommandError(
                f"Address {address} is already registered as {clash.symbol}. "
                "One token address maps to one symbol."
            )

        defaults = {
            "chain_id": chain_id,
            "address": address,
            "decimals": decimals,
            "enabled": not options["disable"],
        }
        if options["min_claim"] is not None:
            defaults["minimum_claim"] = options["min_claim"]
        if options["max_claim"] is not None:
            defaults["maximum_claim"] = options["max_claim"]

        token, created = TokenConfig.objects.update_or_create(symbol=symbol, defaults=defaults)
        verb = "Registered" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {token.symbol} on chain {token.chain_id}: {token.address} "
                f"({token.decimals} decimals, enabled={token.enabled})."
            )
        )
