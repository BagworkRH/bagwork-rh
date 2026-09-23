from django.urls import path

from . import views

app_name = "blockchain"

urlpatterns = [
    path("status/", views.blockchain_status, name="status"),
    path("control/", views.control, name="control"),
    path("listen/", views.listen, name="listen"),
]