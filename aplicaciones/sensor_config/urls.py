from django.urls import path

from . import views

urlpatterns = [
    path("", views.sensor_configuration, name="sensor_configuration"),
    path(
        "<int:sensor_pk>/",
        views.sensor_configuration_detail,
        name="sensor_configuration_detail",
    ),
]
