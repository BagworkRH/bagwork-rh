from django.urls import path

from . import views

app_name = "campaigns"

urlpatterns = [
    # GET is public; POST creates a campaign and is staff-only.
    path("", views.campaign_collection, name="campaign-collection"),
    path("stats/", views.platform_stats_view, name="platform-stats"),
    # GET is public; PATCH edits and is staff-only.
    path("<slug:slug>/", views.campaign_detail, name="campaign-detail"),
    path("<slug:slug>/launch/", views.campaign_launch, name="campaign-launch"),
    path("<int:pk>/join/", views.campaign_join, name="campaign-join"),
]