from django.db import migrations

MODULE_CODE = "ndvi"


def deactivate_ndvi_module(apps, schema_editor):
    platform_module = apps.get_model("core", "PlatformModule")
    platform_module.objects.filter(code=MODULE_CODE).update(is_active=False)


def reactivate_ndvi_module(apps, schema_editor):
    platform_module = apps.get_model("core", "PlatformModule")
    platform_module.objects.filter(code=MODULE_CODE).update(is_active=True)


class Migration(migrations.Migration):
    dependencies = [("core", "0006_satellite_module")]
    operations = [
        migrations.RunPython(
            deactivate_ndvi_module,
            reactivate_ndvi_module,
        )
    ]
