from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sensor_config", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="clientsensor",
            name="is_active",
            field=models.BooleanField(
                default=True,
                help_text="Refleja el estado reportado por la fuente externa.",
                verbose_name="activo en fuente",
            ),
        ),
        migrations.AddField(
            model_name="clientsensor",
            name="dashboard_enabled",
            field=models.BooleanField(
                default=True,
                help_text="Control local de OSIRIS. No modifica el sensor ni la base externa.",
                verbose_name="visible en dashboard",
            ),
        ),
    ]
