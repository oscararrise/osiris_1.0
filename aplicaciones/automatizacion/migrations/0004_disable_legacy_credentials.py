from django.db import migrations


def disable_legacy_credentials(apps, schema_editor):
    legacy_credentials = apps.get_model("automatizacion", "data")
    legacy_credentials.objects.update(clave="!disabled-use-django-auth")


class Migration(migrations.Migration):
    dependencies = [("automatizacion", "0003_sensorreading")]
    operations = [migrations.RunPython(disable_legacy_credentials, migrations.RunPython.noop)]
