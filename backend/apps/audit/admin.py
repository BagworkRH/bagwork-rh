from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "actor", "object_type", "object_id", "created_at")
    list_filter = ("action",)
    search_fields = ("action", "object_type", "object_id", "actor__email")
    readonly_fields = ("action", "actor", "object_type", "object_id", "metadata", "created_at")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):  # append-only
        return False

    def has_change_permission(self, request, obj=None):
        return False