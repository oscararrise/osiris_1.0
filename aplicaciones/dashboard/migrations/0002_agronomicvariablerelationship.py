from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_sensor_configuration_module"),
        ("dashboard", "0001_sensorautomationpolicy"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AgronomicVariableRelationship",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("sensor_id", models.CharField(max_length=160, verbose_name="sensor externo")),
                ("sensor_name", models.CharField(blank=True, max_length=200, verbose_name="nombre del sensor")),
                ("crop_name", models.CharField(max_length=160, verbose_name="cultivo")),
                ("name", models.CharField(max_length=200, verbose_name="nombre de la relación")),
                (
                    "relationship_type",
                    models.CharField(
                        choices=[
                            ("climate", "Clima y transpiración"),
                            ("root_zone", "Zona radicular / fertirriego"),
                            ("photosynthesis", "Fotosíntesis y crecimiento"),
                            ("disease_risk", "Riesgo sanitario"),
                            ("custom", "Personalizada"),
                        ],
                        default="custom",
                        max_length=32,
                        verbose_name="tipo de relación",
                    ),
                ),
                ("variable_ids", models.JSONField(default=list, verbose_name="IDs de variables")),
                ("variable_names", models.JSONField(default=list, verbose_name="nombres de variables")),
                (
                    "agronomic_goal",
                    models.CharField(blank=True, max_length=500, verbose_name="objetivo agronómico"),
                ),
                (
                    "expert_guidance",
                    models.TextField(blank=True, max_length=2500, verbose_name="interpretación agronómica"),
                ),
                ("is_enabled", models.BooleanField(default=True, verbose_name="activa")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agronomic_variable_relationships",
                        to="core.client",
                        verbose_name="cliente",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_agronomic_relationships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "relación agronómica de variables",
                "verbose_name_plural": "relaciones agronómicas de variables",
                "ordering": ("client__name", "crop_name", "sensor_name", "name"),
            },
        ),
        migrations.AddConstraint(
            model_name="agronomicvariablerelationship",
            constraint=models.UniqueConstraint(
                fields=("client", "sensor_id", "name"),
                name="unique_agronomic_relationship_name_per_sensor",
            ),
        ),
    ]
