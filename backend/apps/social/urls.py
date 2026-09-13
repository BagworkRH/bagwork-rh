from django.urls import path

from . import views

app_name = "social"

urlpatterns = [
    path("connect/", views.x_connect, name="x-connect"),
    path("callback/", views.x_callback, name="x-callback"),
    path("disconnect/", views.x_disconnect, name="x-disconnect"),
]