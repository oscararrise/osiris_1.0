from django.urls import path

from . import views

app_name = "satellite"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
]
