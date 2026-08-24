from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0004_add_telemetry_adapter"),
    ]

    operations = [
        migrations.CreateModel(
            name="SensorAutomationPolicy",
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
                (
                    "sensor_name",
                    models.CharField(blank=True, max_length=200, verbose_name="nombre del sensor"),
                ),
                ("is_enabled", models.BooleanField(default=True, verbose_name="automatización activa")),
                ("metric_id", models.CharField(blank=True, max_length=120, verbose_name="métrica")),
                (
                    "metric_name",
                    models.CharField(blank=True, max_length=160, verbose_name="nombre de métrica"),
                ),
                (
                    "operator",
                    models.CharField(
                        choices=[
                            ("gt", "Mayor que"),
                            ("gte", "Mayor o igual que"),
                            ("lt", "Menor que"),
                            ("lte", "Menor o igual que"),
                        ],
                        default="gt",
                        max_length=8,
                        verbose_name="operador",
                    ),
                ),
                ("threshold_value", models.FloatField(blank=True, null=True, verbose_name="umbral")),
                (
                    "cooldown_minutes",
                    models.PositiveIntegerField(default=30, verbose_name="cooldown en minutos"),
                ),
                ("email_enabled", models.BooleanField(default=False, verbose_name="notificar por email")),
                (
                    "email_recipients",
                    models.CharField(blank=True, max_length=500, verbose_name="destinatarios email"),
                ),
                (
                    "whatsapp_enabled",
                    models.BooleanField(default=False, verbose_name="notificar por WhatsApp"),
                ),
                (
                    "whatsapp_recipients",
                    models.CharField(blank=True, max_length=500, verbose_name="destinatarios WhatsApp"),
                ),
                (
                    "automation_level",
                    models.CharField(
                        choices=[
                            ("monitor", "Nivel 0 · Solo monitorear"),
                            ("notify", "Nivel 1 · Notificar"),
                            ("recommend", "Nivel 2 · IA recomienda una acción"),
                            ("supervised", "Nivel 3 · IA prepara la acción"),
                            ("autonomous", "Nivel 4 · IA puede actuar automáticamente"),
                        ],
                        default="recommend",
                        max_length=20,
                        verbose_name="nivel de automatización",
                    ),
                ),
                (
                    "requires_confirmation",
                    models.BooleanField(default=True, verbose_name="requiere confirmación humana"),
                ),
                (
                    "ai_instruction",
                    models.TextField(
                        blank=True,
                        help_text=(
                            "Contexto operativo que la IA debe considerar antes de proponer "
                            "o ejecutar acciones."
                        ),
                        max_length=2500,
                        verbose_name="instrucción para la IA",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sensor_automation_policies",
                        to="core.client",
                        verbose_name="cliente",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_sensor_automation_policies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "política de automatización de sensor",
                "verbose_name_plural": "políticas de automatización de sensores",
                "ordering": ("client__name", "sensor_name", "sensor_id"),
            },
        ),
        migrations.AddConstraint(
            model_name="sensorautomationpolicy",
            constraint=models.UniqueConstraint(
                fields=("client", "sensor_id"),
                name="unique_sensor_automation_policy_per_client",
            ),
        ),
    ]
