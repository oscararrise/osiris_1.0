from django.db import migrations

MODULES = (
    (
        "dashboard",
        "Dashboard",
        "Sensores, tendencias, salud técnica y alertas.",
        "s2",
        "Monitoreo",
        10,
    ),
    (
        "monitoring",
        "Monitoreo",
        "Vista operativa de variables y dispositivos.",
        "s1",
        "Monitoreo",
        20,
    ),
    (
        "control",
        "Control",
        "Acciones y seguimiento de control operativo.",
        "s3",
        "Operación",
        30,
    ),
    (
        "ndvi",
        "Índices NDVI",
        "Análisis de vigor y cobertura vegetal.",
        "nvid",
        "Analítica",
        40,
    ),
    (
        "ai",
        "Inteligencia artificial",
        "Herramientas de análisis asistido.",
        "ia",
        "Analítica",
        50,
    ),
    (
        "chat",
        "Asistente",
        "Consultas conversacionales sobre la operación.",
        "chat",
        "Analítica",
        60,
    ),
    (
        "drones",
        "Drones",
        "Planeación y consulta de vuelos e imágenes.",
        "drones",
        "Campo",
        70,
    ),
    ("fences", "Cercas", "Supervisión de perímetros y zonas.", "cercas", "Campo", 80),
    (
        "vision",
        "Visión artificial",
        "Detección y clasificación de imágenes.",
        "yolov5",
        "Analítica",
        90,
    ),
    (
        "reports",
        "Reportes",
        "Informes consolidados de la operación.",
        "reported",
        "Gestión",
        100,
    ),
    (
        "support",
        "Soporte",
        "Solicitudes y acompañamiento técnico.",
        "support",
        "Gestión",
        110,
    ),
)


def seed_modules(apps, schema_editor):
    platform_module = apps.get_model("core", "PlatformModule")
    for code, name, description, route_name, category, sort_order in MODULES:
        platform_module.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "route_name": route_name,
                "category": category,
                "sort_order": sort_order,
                "is_active": True,
            },
        )


def unseed_modules(apps, schema_editor):
    platform_module = apps.get_model("core", "PlatformModule")
    platform_module.objects.filter(code__in=[module[0] for module in MODULES]).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(seed_modules, unseed_modules)]
