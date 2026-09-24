from django.contrib import admin, messages

from .models import SellerProfile
from .services import set_seller_status


@admin.action(description="Activate selected sellers")
def activate_sellers(modeladmin, request, queryset):
    for profile in queryset:
        set_seller_status(profile, "ACTIVE", "Activated from admin.", actor=request.user)
    messages.success(request, f"Activated {queryset.count()} seller(s).")


@admin.action(description="Suspend selected sellers (blocks new claims/joins)")
def suspend_sellers(modeladmin, request, queryset):
    for profile in queryset:
        set_seller_status(profile, "SUSPENDED", "Suspended from admin.", actor=request.user)
    messages.warning(request, f"Suspended {queryset.count()} seller(s).")


@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = ("seller_code", "display_name", "user", "status", "reputation_score", "created_at")
    search_fields = ("seller_code", "display_name", "user__email")
    list_filter = ("status",)
    readonly_fields = ("seller_code", "created_at", "updated_at")
    date_hierarchy = "created_at"
    actions = [activate_sellers, suspend_sellers]
    list_select_related = ("user",)

    def has_delete_permission(self, request, obj=None):
        # Sellers own financial history; suspend instead of deleting (Spec 05).
        return False