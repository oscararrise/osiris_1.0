from django.contrib import admin
from django.urls import include, path

from aplicaciones.automatizacion import views as legacy_views
from aplicaciones.core.decorators import module_access_required
from aplicaciones.core.views import sensor_dashboard

admin.site.site_header = "Administración OSIRIS"
admin.site.site_title = "OSIRIS"
admin.site.index_title = "Clientes, usuarios y módulos"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("aplicaciones.core.urls")),
    path("sensor-config/", include("aplicaciones.sensor_config.urls")),
    path("s2", sensor_dashboard, name="s2"),
    path("s1", module_access_required("monitoring")(legacy_views.s1), name="s1"),
    path("control", module_access_required("control")(legacy_views.s3), name="s3"),
    path(
        "support",
        module_access_required("support")(legacy_views.support),
        name="support",
    ),
    path(
        "enviar_mail",
        module_access_required("support")(legacy_views.enviar_mail),
        name="enviar_mail",
    ),
    path("yolov5", module_access_required("vision")(legacy_views.yolov5), name="yolov5"),
    path("chat", module_access_required("chat")(legacy_views.chat), name="chat"),
    path("ia", module_access_required("ai")(legacy_views.ia), name="ia"),
    path("cercas", module_access_required("fences")(legacy_views.cercas), name="cercas"),
    path(
        "reported",
        module_access_required("reports")(legacy_views.reported),
        name="reported",
    ),
    path("nvid", module_access_required("ndvi")(legacy_views.nvid), name="nvid"),
    path("drones", module_access_required("drones")(legacy_views.drones), name="drones"),
    path(
        "actualizar_control_data/",
        module_access_required("control")(legacy_views.actualizar_control_data),
        name="actualizar_control_data",
    ),
]
