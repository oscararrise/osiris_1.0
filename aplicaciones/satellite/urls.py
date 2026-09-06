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
]
