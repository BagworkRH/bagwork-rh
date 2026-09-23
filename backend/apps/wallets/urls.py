from django.urls import path

from . import views

app_name = "wallets"

urlpatterns = [
    path("", views.claim_create, name="claim-create"),
    path("<int:pk>/", views.claim_detail, name="claim-detail"),
    path("<int:pk>/authorization/", views.claim_authorization, name="claim-authorization"),
    path("<int:pk>/submit/", views.claim_submit, name="claim-submit"),
]