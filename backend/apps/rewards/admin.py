from django.contrib import admin, messages

from .models import Reward

REWARD_REVIEW_HELP = (
    "Rewards are approved, released, or reversed through the audited reward "
    "service; use the back-office API (POST /api/v1/admin/rewards/<id>/review/) "
    "or the admin actions below."
)


@admin.action(description="Approve selected rewards (PENDING -> APPROVED)")
def approve_rewards(modeladmin, request, queryset):
    from .exceptions import RewardEngineError  # noqa: PLC0415
    from .services import approve_reward  # noqa: PLC0415

    done = 0
    for reward in queryset:
        try:
            approve_reward(reward, actor=request.user)
            done += 1
        except RewardEngineError as exc:
            messages.error(request, f"Reward {reward.pk}: {exc}")
    messages.success(request, f"Approved {done} reward(s).")


@admin.action(description="Release selected rewards (APPROVED -> AVAILABLE)")
def release_rewards(modeladmin, request, queryset):
    from .exceptions import RewardEngineError  # noqa: PLC0415
    from .services import make_available  # noqa: PLC0415

    done = 0
    for reward in queryset:
        try:
            make_available(reward, actor=request.user)
            done += 1
        except RewardEngineError as exc:
            messages.error(request, f"Reward {reward.pk}: {exc}")
    messages.success(request, f"Released {done} reward(s) to sellers.")


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
    actions = [approve_rewards, release_rewards]
    help_texts = {"status": REWARD_REVIEW_HELP}

    def has_delete_permission(self, request, obj=None):
        # Financial records are never deleted (Spec 03: never silently modify).
        return False