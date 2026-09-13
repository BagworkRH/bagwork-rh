from django.contrib import admin

from .models import PostMetricSnapshot, SocialPost, XAccount


@admin.register(XAccount)
class XAccountAdmin(admin.ModelAdmin):
    list_display = (
        "username", "display_name", "provider_user_id", "seller",
        "status", "connected_at", "last_synced_at",
    )
    search_fields = ("username", "provider_user_id", "seller__seller_code")
    list_filter = ("status",)
    readonly_fields = ("encrypted_credentials", "credentials_iv", "token_expiry", "scopes")
    date_hierarchy = "connected_at"


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = (
        "external_post_id", "seller", "campaign",
        "verification_status", "published_at", "discovered_at",
    )
    list_filter = ("verification_status",)
    search_fields = ("external_post_id", "seller__seller_code", "campaign__name")
    date_hierarchy = "published_at"


@admin.register(PostMetricSnapshot)
class PostMetricSnapshotAdmin(admin.ModelAdmin):
    list_display = ("post", "collected_at", "impressions", "likes", "reposts", "replies")
    date_hierarchy = "collected_at"