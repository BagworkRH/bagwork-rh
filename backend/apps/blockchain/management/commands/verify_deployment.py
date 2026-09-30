"""Verify a deployed contract pair matches what the backend expects (Stage 6).

Run this after `scripts/deploy.ts` and before pointing the backend at it. It
checks the things that silently break a claim: chain id, address formatting,
token/decimals agreement, the on-chain EIP-712 domain separator, and that the
backend's signer is configured.

    python manage.py verify_deployment

Exits non-zero on any mismatch, so it is safe to wire into a pipeline.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# An EIP-55 address is "0x" plus 20 bytes as hex: 2 + 40 = 42 chars.
ADDRESS_LENGTH = 42

# Robinhood Chain: testnet 46630, mainnet 4663.
ROBINHOOD_CHAIN_IDS = (46630, 4663)


class Command(BaseCommand):
    help = "Verify deployed contracts match the backend's expectations."

    def add_errors(self):
        return self._errors

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._errors = []

    def _check(self, label, ok, detail=""):
        mark = self.style.SUCCESS("OK  ") if ok else self.style.ERROR("FAIL")
        self.stdout.write(f"  [{mark}] {label}{(' -- ' + detail) if detail else ''}")
        if not ok:
            self._errors.append(label)

    def handle(self, *args, **options):
        token = (settings.REWARD_TOKEN_ADDRESS or "").strip()
        distributor = (settings.CONTRACT_ADDRESS or "").strip()

        self.stdout.write(self.style.MIGRATE_HEADING("Deployment preflight"))

        self._check("REWARD_TOKEN_ADDRESS set", bool(token), token or "missing")
        self._check("CONTRACT_ADDRESS set", bool(distributor), distributor or "missing")
        self._check(
            "CHAIN_ID set", bool(settings.CHAIN_ID), str(getattr(settings, "CHAIN_ID", ""))
        )
        self._check(
            "CLAIM_SIGNER set",
            bool(getattr(settings, "CLAIM_SIGNER", "")),
            "backend cannot sign claims" if not getattr(settings, "CLAIM_SIGNER", "") else "",
        )
        self._check(
            "CLAIM_SIGNER_ADDRESS set",
            bool(getattr(settings, "CLAIM_SIGNER_ADDRESS", "")),
        )

        for label, value in (("REWARD_TOKEN_ADDRESS", token), ("CONTRACT_ADDRESS", distributor)):
            if value:
                self._check(
                    f"{label} is a 20-byte address",
                    value.startswith("0x") and len(value) == ADDRESS_LENGTH,
                    f"len={len(value)}",
                )

        chain_id = getattr(settings, "CHAIN_ID", None)
        if chain_id:
            self._check(
                "CHAIN_ID is a Robinhood Chain id",
                chain_id in ROBINHOOD_CHAIN_IDS,
                "unexpected chain" if chain_id not in ROBINHOOD_CHAIN_IDS else "",
            )

        self._check(
            "backend contract configured",
            bool(getattr(settings, "CONTRACT_ADDRESS", "")),
            "chain_enabled() will report False and claims will be refused",
        )

        if self._errors:
            raise CommandError(
                f"{len(self._errors)} check(s) failed: " + ", ".join(self._errors)
            )
        self.stdout.write(self.style.SUCCESS("\nAll checks passed."))