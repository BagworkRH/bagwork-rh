from django.contrib import admin

from .models import Reward


@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin):
    list_display = (
        "pk", "seller", "campaign", "amount", "token_symbol",
        "status", "created_at", "approved_at",
    )
    list_filter = ("status", "token_symbol", "chain_id", "calculation_version")
    search_fields = ("seller__seller_code", "campaign__name", "explanation")
    readonly_fields = (
        "gross_amount", "deduction_amount", "explanation",
        "calculation_version", "created_at",
    )
    date_hierarchy = "created_at"