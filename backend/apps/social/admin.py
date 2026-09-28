from django.contrib import admin, messages

from .models import PostMetricSnapshot, SocialAccount, SocialPost


@admin.action(description="Approve selected posts (mark VERIFIED)")
def approve_posts(modeladmin, request, queryset):
    from apps.rewards.exceptions import RewardEngineError  # noqa: PLC0415

    from .post_services import review_post  # noqa: PLC0415

    done = 0
    for post in queryset:
        try:
            review_post(post, "approve", actor=request.user)
            done += 1
        except RewardEngineError as exc:  # pragma: no cover - defensive
            messages.error(request, f"Post {post.pk}: {exc}")
    messages.success(request, f"Approved {done} post(s).")


@admin.action(description="Mark selected posts SUSPICIOUS_ACTIVITY")
def flag_posts_suspicious(modeladmin, request, queryset):
    from .post_services import review_post  # noqa: PLC0415

    for post in queryset:
        review_post(
            post,
            "reject",
            "Flagged by admin review.",
            "SUSPICIOUS_ACTIVITY",
            actor=request.user,
        )
    messages.warning(request, f"Flagged {queryset.count()} post(s) as suspicious.")


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
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
    actions = [approve_posts, flag_posts_suspicious]
    readonly_fields = ("rejection_reason", "updated_at")


@admin.register(PostMetricSnapshot)
class PostMetricSnapshotAdmin(admin.ModelAdmin):
    list_display = ("post", "collected_at", "impressions", "likes", "reposts", "replies")
    date_hierarchy = "collected_at"