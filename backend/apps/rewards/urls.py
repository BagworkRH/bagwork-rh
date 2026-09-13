from django.urls import path

from . import views

app_name = "rewards"

urlpatterns = [
    path("", views.reward_list, name="reward-list"),
    path("<int:pk>/", views.reward_detail, name="reward-detail"),
    path("<int:pk>/approve/", views.reward_approve, name="reward-approve"),
    path("<int:pk>/available/", views.reward_available, name="reward-available"),
    path("<int:pk>/reverse/", views.reward_reverse, name="reward-reverse"),
]