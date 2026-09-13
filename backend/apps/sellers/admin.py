from django.contrib import admin

from .models import SellerProfile


@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = ("seller_code", "display_name", "user", "status", "reputation_score", "created_at")
    search_fields = ("seller_code", "display_name", "user__email")
    list_filter = ("status",)
    readonly_fields = ("seller_code", "created_at", "updated_at")
    date_hierarchy = "created_at"