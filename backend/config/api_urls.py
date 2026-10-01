"""Versioned API URL configuration under /api/v1/.

Endpoints described in Spec 02:
  /auth/*   register, login, logout
  /me/*     user, seller, wallets, rewards, claims
  /campaigns/, /x/, /posts/, /rewards/, /claims/
  /blockchain/  chain status + emergency controls
  /admin/*      staff-only back-office (Spec 05 Phase 7); Django admin is at /admin/
"""
from django.urls import include, path

urlpatterns = [
    # Brand onboarding and USDC funding sit at /api/v1/brand/ rather than
    # nested under campaigns/, because a brand exists before it has any
    # campaign: onboarding must not require a campaign to exist first.
    path("brand/", include("apps.campaigns.brand_urls")),
    path("auth/", include("apps.accounts.urls")),
    path("me/", include("apps.sellers.urls")),
    path("campaigns/", include("apps.campaigns.urls")),
    path("x/", include("apps.social.urls")),
    path("posts/", include("apps.social.post_urls")),
    path("rewards/", include("apps.rewards.urls")),
    path("claims/", include("apps.wallets.urls")),
    path("blockchain/", include("apps.blockchain.urls")),
    path("admin/", include("apps.audit.admin_urls")),
]