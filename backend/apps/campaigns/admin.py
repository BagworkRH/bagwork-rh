from django.contrib import admin, messages

from .models import Campaign, CampaignParticipation
from .services import set_campaign_status


@admin.action(description="Pause selected campaigns (disables claiming)")
def pause_campaigns(modeladmin, request, queryset):
    for campaign in queryset:
        set_campaign_status(campaign, "PAUSED", "Paused from admin.", actor=request.user)
    messages.warning(request, f"Paused {queryset.count()} campaign(s).")


@admin.action(description="Activate selected campaigns")
def activate_campaigns(modeladmin, request, queryset):
    for campaign in queryset:
        set_campaign_status(campaign, "ACTIVE", "Activated from admin.", actor=request.user)
    messages.success(request, f"Activated {queryset.count()} campaign(s).")


@admin.action(description="End selected campaigns")
def end_campaigns(modeladmin, request, queryset):
    for campaign in queryset:
        set_campaign_status(campaign, "ENDED", "Ended from admin.", actor=request.user)
    messages.info(request, f"Ended {queryset.count()} campaign(s).")


class ParticipationInline(admin.TabularInline):
    model = CampaignParticipation
    extra = 0
    readonly_fields = ("seller", "status", "joined_at", "cumulative_reward")


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = (
        "name", "project_name", "status", "reward_model", "budget",
        "remaining_budget", "start_at", "end_at",
    )
    list_filter = ("status", "reward_model", "chain_id")
    search_fields = ("name", "slug", "project_name")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("remaining_budget", "created_at", "updated_at")
    inlines = [ParticipationInline]
    date_hierarchy = "start_at"
    actions = [pause_campaigns, activate_campaigns, end_campaigns]


@admin.register(CampaignParticipation)
class CampaignParticipationAdmin(admin.ModelAdmin):
    list_display = ("seller", "campaign", "status", "joined_at", "cumulative_reward")
    list_filter = ("status",)
    search_fields = ("seller__seller_code", "campaign__name")
    readonly_fields = ("cumulative_reward", "joined_at")