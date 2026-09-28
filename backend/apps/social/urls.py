from django.urls import path

from . import views

app_name = "social"

# Platform-agnostic routes. `platform` is part of the path so a callback can
# never be completed against the wrong provider.
urlpatterns = [
    path("platforms/", views.platforms, name="platforms"),
    path("<str:platform>/connect/", views.connect, name="connect"),
    path("<str:platform>/callback/", views.callback, name="callback"),
    path("<str:platform>/disconnect/", views.disconnect, name="disconnect"),
]