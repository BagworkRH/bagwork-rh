from django.urls import path

from . import views

app_name = "wallets"

urlpatterns = [
    path("", views.claim_create, name="claim-create"),
    path("<int:pk>/", views.claim_detail, name="claim-detail"),
]