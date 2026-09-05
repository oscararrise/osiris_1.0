from django.db import migrations

MODULE_CODE = "sensor_configuration"


def add_sensor_configuration_module(apps, schema_editor):
    platform_module = apps.get_model("core", "PlatformModule")
    client_module = apps.get_model("core", "ClientModule")
    client_data_source = apps.get_model("core", "ClientDataSource")

    module, _ = platform_module.objects.update_or_create(
        code=MODULE_CODE,
        defaults={
            "name": "Configuración de sensores",
            "description": "Ubicación física, zonas y contexto operativo de cada sensor.",
            "route_name": "sensor_configuration",
            "icon": "fa-solid fa-location-dot",
            "category": "Configuración",
            "sort_order": 15,
            "is_active": True,
        },
    )

    aranet_client_ids = client_data_source.objects.filter(
        adapter_key="aranet",
        is_active=True,
    ).values_list("client_id", flat=True)
    for client_id in aranet_client_ids:
        client_module.objects.update_or_create(
            client_id=client_id,
            module=module,
            defaults={
                "is_enabled": True,
                "minimum_access_level": 30,
            },
        )


def remove_sensor_configuration_module(apps, schema_editor):
    platform_module = apps.get_model("core", "PlatformModule")
    platform_module.objects.filter(code=MODULE_CODE).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0004_add_telemetry_adapter")]
    operations = [
        migrations.RunPython(
            add_sensor_configuration_module,
            remove_sensor_configuration_module,
        )
    ]
