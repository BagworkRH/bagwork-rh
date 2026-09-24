"""Django admin for the audit trail and the fraud/risk review queue (Spec 05 Phase 7).

The audit log is append-only and the review queue is decision-driven: flags are
dismissed or confirmed by a human, and every decision is itself audited.
"""
from django.contrib import admin, messages

from . import risk
from .models import AuditLog, RiskFlag


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "actor", "object_type", "object_id", "created_at")
    list_filter = ("action", "object_type")
    search_fields = ("action", "object_type", "object_id", "actor__email")
    readonly_fields = ("action", "actor", "object_type", "object_id", "metadata", "created_at")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):  # append-only
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.action(description="Dismiss selected risk flags (no action taken)")
def dismiss_flags(modeladmin, request, queryset):
    for flag in queryset:
        risk.resolve_flag(flag, "dismiss", flag.note, actor=request.user)
    messages.success(request, f"Dismissed {queryset.count()} risk flag(s).")


@admin.action(description="Confirm selected risk flags (follow-up required)")
def confirm_flags(modeladmin, request, queryset):
    for flag in queryset:
        risk.resolve_flag(flag, "confirm", flag.note, actor=request.user)
    messages.warning(request, f"Confirmed {queryset.count()} risk flag(s); follow up manually.")


@admin.register(RiskFlag)
class RiskFlagAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "subject_type",
        "subject_id",
        "seller",
        "score",
        "severity",
        "status",
        "created_at",
    )
    list_filter = ("status", "severity", "subject_type")
    search_fields = ("subject_id", "seller__seller_code", "note")
    readonly_fields = (
        "subject_type",
        "subject_id",
        "seller",
        "score",
        "severity",
        "signals",
        "resolved_by",
        "resolved_at",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
    actions = [dismiss_flags, confirm_flags]
    fieldsets = (
        (None, {"fields": ("subject_type", "subject_id", "seller", "score", "severity")}),
        ("Evidence", {"fields": ("signals",)}),
        ("Review", {"fields": ("status", "note", "resolved_by", "resolved_at")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def get_readonly_fields(self, request, obj=None):
        # Decisions go through the audited admin actions (and the staff API) so
        # every status change leaves a trace; fields stay read-only here.
        return [*self.readonly_fields, "status", "note"]

    def has_add_permission(self, request):  # flags are only produced by scoring
        return False