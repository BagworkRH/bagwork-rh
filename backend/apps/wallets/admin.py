from django.contrib import admin, messages

from .models import Claim, Wallet


@admin.action(description="Mark selected claims FAILED (releases the reward)")
def fail_claims(modeladmin, request, queryset):
    from apps.rewards.exceptions import RewardEngineError  # noqa: PLC0415

    from .services import mark_claim_failed  # noqa: PLC0415

    done = 0
    for claim in queryset:
        try:
            mark_claim_failed(claim, "Marked failed by admin review.", actor=request.user)
            done += 1
        except RewardEngineError as exc:
            messages.error(request, f"Claim {claim.pk}: {exc}")
    messages.warning(request, f"Marked {done} claim(s) as failed.")


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("address", "seller", "chain_id", "network", "verified", "connected_at")
    list_filter = ("verified", "network", "chain_id")
    search_fields = ("address", "seller__seller_code")
    date_hierarchy = "connected_at"
    list_select_related = ("seller",)


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("pk", "seller", "amount", "token_symbol", "status", "transaction_hash", "created_at")
    list_filter = ("status", "chain_id", "token_symbol")
    search_fields = ("seller__seller_code", "transaction_hash", "wallet__address")
    readonly_fields = ("created_at", "confirmed_at", "nonce", "signed_authorization")
    date_hierarchy = "created_at"
    actions = [fail_claims]
    list_select_related = ("seller", "wallet")

    def has_delete_permission(self, request, obj=None):
        # On-chain claims are financial records (Spec 02/04).
        return False