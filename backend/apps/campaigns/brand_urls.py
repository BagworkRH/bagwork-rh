"""Brand-facing routes, mounted at /api/v1/brand/.

Kept separate from the campaign URLs because a brand exists before it has any
campaign: onboarding, funding and quoting must not require a campaign first.
"""
from django.urls import path

from . import brand_api

app_name = "brand"

urlpatterns = [
    path("profile/", brand_api.brand_profile, name="brand-profile"),
    path("funding/", brand_api.brand_funding, name="brand-funding"),
    path(
        "funding/<int:pk>/confirm/",
        brand_api.brand_funding_confirm,
        name="brand-funding-confirm",
    ),
    path("quote/", brand_api.brand_quote, name="brand-quote"),
    path("campaigns/", brand_api.brand_campaigns, name="brand-campaigns"),
]
