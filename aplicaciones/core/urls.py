from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.root, name="home"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="core/login.html", redirect_authenticated_user=True
        ),
        name="login",
    ),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    # Compatibilidad con las plantillas legacy de OSIRIS 1.0 que hacen POST a /salir.
    path("salir", auth_views.LogoutView.as_view(), name="logout_legacy"),
    path("inicio/", views.operations, name="inicio"),
]
