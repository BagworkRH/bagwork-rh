"""Versioned API URL configuration under /api/v1/.

Endpoints described in Spec 02:
  /auth/*   register, login, logout
  /me/*     user, seller, wallets, rewards, claims
  /campaigns/, /x/, /posts/, /rewards/, /claims/
"""
from django.urls import include, path

urlpatterns = [
    path("auth/", include("apps.accounts.urls")),
    path("me/", include("apps.sellers.urls")),
    path("campaigns/", include("apps.campaigns.urls")),
    path("x/", include("apps.social.urls")),
    path("posts/", include("apps.social.post_urls")),
    path("rewards/", include("apps.rewards.urls")),
    path("claims/", include("apps.wallets.urls")),
]