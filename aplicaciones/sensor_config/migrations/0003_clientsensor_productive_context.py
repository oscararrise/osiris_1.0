from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sensor_config", "0002_clientsensor_dashboard_enabled")]

    operations = [
        migrations.AddField(
            model_name="clientsensor",
            name="activity_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("crop", "Cultivo"),
                    ("poultry", "Avicultura"),
                    ("livestock", "Ganadería"),
                    ("aquaculture", "Acuicultura"),
                    ("storage", "Almacenamiento / cadena de frío"),
                    ("other", "Otro"),
                ],
                default="",
                help_text="Contexto productivo local de OSIRIS.",
                max_length=24,
                verbose_name="actividad",
            ),
        ),
        migrations.AddField(
            model_name="clientsensor",
            name="product_name",
            field=models.CharField(
                blank=True,
                help_text="Ej. Arándano, Fresa, Tomate o Gallinas.",
                max_length=160,
                verbose_name="producto / especie",
            ),
        ),
    ]
