"""Blockchain app (Phase 6): claims signing, listener, ledger, reconciliation."""
from django.apps import AppConfig


class BlockchainConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.blockchain"
    verbose_name = "Blockchain"