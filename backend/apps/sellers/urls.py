from django.urls import path

from . import views

app_name = "sellers"

urlpatterns = [
    path("", views.me, name="me"),
    path("seller/", views.seller_profile, name="seller-profile"),
    path("wallets/", views.my_wallets, name="my-wallets"),
    path("rewards/", views.my_rewards, name="my-rewards"),
    path("claims/", views.my_claims, name="my-claims"),
    path("dashboard/", views.dashboard, name="dashboard"),
]