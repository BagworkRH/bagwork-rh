from django.contrib import admin

from .models import LedgerEntry, PlatformControl, TokenConfig


@admin.register(TokenConfig)
class TokenConfigAdmin(admin.ModelAdmin):
    list_display = ("symbol", "chain_id", "address", "decimals", "enabled", "created_at")
    list_filter = ("chain_id", "enabled")
    search_fields = ("symbol", "address")
    readonly_fields = ("created_at", "updated_at")


@admin.register(PlatformControl)
class PlatformControlAdmin(admin.ModelAdmin):
    list_display = ("key", "claiming_paused", "updated_at")
    readonly_fields = ("key", "updated_at")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "id", "action", "token_symbol", "amount", "seller", "reward",
        "claim", "transaction_hash", "created_at",
    )
    list_filter = ("action", "token_symbol")
    search_fields = ("transaction_hash", "seller__seller_code", "reward__pk", "claim__pk")
    readonly_fields = tuple(
        f.name for f in LedgerEntry._meta.fields if f.name != "id"
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):  # append-only
        return False

    def has_change_permission(self, request, obj=None):
        return False