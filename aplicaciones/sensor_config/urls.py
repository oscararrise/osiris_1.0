from django.urls import path

from . import views

urlpatterns = [
    path("", views.sensor_configuration, name="sensor_configuration"),
    path(
        "<int:sensor_pk>/dashboard/",
        views.toggle_sensor_dashboard,
        name="sensor_configuration_toggle",
    ),
    path(
        "<int:sensor_pk>/",
        views.sensor_configuration_detail,
        name="sensor_configuration_detail",
    ),
]
