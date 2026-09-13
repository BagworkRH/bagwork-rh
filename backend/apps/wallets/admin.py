from django.contrib import admin

from .models import Claim, Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("address", "seller", "chain_id", "network", "verified", "connected_at")
    list_filter = ("verified", "network", "chain_id")
    search_fields = ("address", "seller__seller_code")
    date_hierarchy = "connected_at"


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("pk", "seller", "amount", "token_symbol", "status", "transaction_hash", "created_at")
    list_filter = ("status", "chain_id", "token_symbol")
    search_fields = ("seller__seller_code", "transaction_hash", "wallet__address")
    readonly_fields = ("created_at", "confirmed_at", "nonce", "signed_authorization")
    date_hierarchy = "created_at"