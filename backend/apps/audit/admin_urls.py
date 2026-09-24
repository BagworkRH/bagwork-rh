"""Staff-only back-office routes, mounted at /api/v1/admin/ (Spec 05 Phase 7)."""
from django.urls import path

from . import admin_api

urlpatterns = [
    path("overview/", admin_api.overview, name="admin-overview"),
    path("sellers/", admin_api.sellers, name="admin-sellers"),
    path("sellers/<int:pk>/status/", admin_api.seller_status, name="admin-seller-status"),
    path("campaigns/", admin_api.campaigns, name="admin-campaigns"),
    path("campaigns/<int:pk>/status/", admin_api.campaign_status, name="admin-campaign-status"),
    path("posts/", admin_api.posts, name="admin-posts"),
    path("posts/<int:pk>/review/", admin_api.post_review, name="admin-post-review"),
    path("rewards/", admin_api.rewards, name="admin-rewards"),
    path("rewards/<int:pk>/review/", admin_api.reward_review, name="admin-reward-review"),
    path("claims/", admin_api.claims, name="admin-claims"),
    path("claims/<int:pk>/fail/", admin_api.claim_fail, name="admin-claim-fail"),
    path("risk/", admin_api.risk_queue, name="admin-risk-queue"),
    path("risk/scan/", admin_api.risk_scan, name="admin-risk-scan"),
    path("risk/<int:pk>/resolve/", admin_api.risk_resolve, name="admin-risk-resolve"),
    path("audit-logs/", admin_api.audit_logs, name="admin-audit-logs"),
    path("settings/", admin_api.settings_overview, name="admin-settings"),
]