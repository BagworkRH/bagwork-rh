from django.contrib import admin

from .models import Campaign, CampaignParticipation


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


@admin.register(CampaignParticipation)
class CampaignParticipationAdmin(admin.ModelAdmin):
    list_display = ("seller", "campaign", "status", "joined_at", "cumulative_reward")
    list_filter = ("status",)
    search_fields = ("seller__seller_code", "campaign__name")
    readonly_fields = ("cumulative_reward", "joined_at")