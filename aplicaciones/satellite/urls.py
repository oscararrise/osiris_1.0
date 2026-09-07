from django.urls import path

from . import views

app_name = "satellite"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path(
        "fields/<int:field_id>/scenes/",
        views.field_scenes,
        name="field_scenes",
    ),
    path(
        "fields/<int:field_id>/search-scenes/",
        views.search_field_scenes,
        name="search_field_scenes",
    ),
    path(
        "scenes/<int:scene_id>/images/request/",
        views.request_scene_images,
        name="request_scene_images",
    ),
    path(
        "scenes/<int:scene_id>/images/refresh/",
        views.refresh_scene_images,
        name="refresh_scene_images",
    ),
]
