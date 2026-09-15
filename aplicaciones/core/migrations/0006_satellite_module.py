from django.db import migrations

MODULE_CODE = "satellite"


def add_satellite_module(apps, schema_editor):
    platform_module = apps.get_model("core", "PlatformModule")
    platform_module.objects.update_or_create(
        code=MODULE_CODE,
        defaults={
            "name": "Monitoreo Satelital",
            "description": "Imágenes, índices y análisis satelital de lotes agrícolas.",
            "route_name": "satellite:dashboard",
            "icon": "fa-solid fa-satellite",
            "category": "Analítica",
            "sort_order": 45,
            "is_active": True,
        },
    )


def remove_satellite_module(apps, schema_editor):
    platform_module = apps.get_model("core", "PlatformModule")
    platform_module.objects.filter(code=MODULE_CODE).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0005_sensor_configuration_module")]
    operations = [
        migrations.RunPython(
            add_satellite_module,
            remove_satellite_module,
        )
    ]
