from django.urls import path

from . import views

app_name = "campaigns"

urlpatterns = [
    path("", views.campaign_list, name="campaign-list"),
    path("stats/", views.platform_stats_view, name="platform-stats"),
    path("<slug:slug>/", views.campaign_detail, name="campaign-detail"),
    path("<int:pk>/join/", views.campaign_join, name="campaign-join"),
]