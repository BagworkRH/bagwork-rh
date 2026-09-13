from django.urls import path

from . import post_views

app_name = "social-posts"

urlpatterns = [
    path("", post_views.post_list, name="post-list"),
    path("submit/", post_views.post_submit, name="post-submit"),
    path("<int:pk>/", post_views.post_detail, name="post-detail"),
    path("<int:pk>/verify/", post_views.post_verify, name="post-verify"),
    path("<int:pk>/calculate-reward/", post_views.post_calculate_reward, name="post-calculate-reward"),
]