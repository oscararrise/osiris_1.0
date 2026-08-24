from __future__ import annotations

from django.conf import settings
from django.db import models

from aplicaciones.core.models import Client


class SensorAutomationPolicy(models.Model):
    """OSIRIS-owned automation preferences for one external sensor.

    Sensor measurements and Aranet rules remain read-only in the client database. This
    model stores only the workflow OSIRIS should follow after an alert is detected.
    """

    class AutomationLevel(models.TextChoices):
        MONITOR = "monitor", "Nivel 0 · Solo monitorear"
        NOTIFY = "notify", "Nivel 1 · Notificar"
        RECOMMEND = "recommend", "Nivel 2 · IA recomienda una acción"
        SUPERVISED = "supervised", "Nivel 3 · IA prepara la acción"
        AUTONOMOUS = "autonomous", "Nivel 4 · IA puede actuar automáticamente"

    class Operator(models.TextChoices):
        GREATER_THAN = "gt", "Mayor que"
        GREATER_EQUAL = "gte", "Mayor o igual que"
        LESS_THAN = "lt", "Menor que"
        LESS_EQUAL = "lte", "Menor o igual que"

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="sensor_automation_policies",
        verbose_name="cliente",
    )
    sensor_id = models.CharField("sensor externo", max_length=160)
    sensor_name = models.CharField("nombre del sensor", max_length=200, blank=True)
    is_enabled = models.BooleanField("automatización activa", default=True)

    metric_id = models.CharField("métrica", max_length=120, blank=True)
    metric_name = models.CharField("nombre de métrica", max_length=160, blank=True)
    operator = models.CharField(
        "operador",
        max_length=8,
        choices=Operator.choices,
        default=Operator.GREATER_THAN,
    )
    threshold_value = models.FloatField("umbral", null=True, blank=True)
    cooldown_minutes = models.PositiveIntegerField("cooldown en minutos", default=30)

    email_enabled = models.BooleanField("notificar por email", default=False)
    email_recipients = models.CharField("destinatarios email", max_length=500, blank=True)
    whatsapp_enabled = models.BooleanField("notificar por WhatsApp", default=False)
    whatsapp_recipients = models.CharField(
        "destinatarios WhatsApp",
        max_length=500,
        blank=True,
    )

    automation_level = models.CharField(
        "nivel de automatización",
        max_length=20,
        choices=AutomationLevel.choices,
        default=AutomationLevel.RECOMMEND,
    )
    requires_confirmation = models.BooleanField("requiere confirmación humana", default=True)
    ai_instruction = models.TextField(
        "instrucción para la IA",
        max_length=2500,
        blank=True,
        help_text="Contexto operativo que la IA debe considerar antes de proponer o ejecutar acciones.",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_sensor_automation_policies",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("client", "sensor_id"),
                name="unique_sensor_automation_policy_per_client",
            )
        ]
        ordering = ("client__name", "sensor_name", "sensor_id")
        verbose_name = "política de automatización de sensor"
        verbose_name_plural = "políticas de automatización de sensores"

    def __str__(self) -> str:
        return f"{self.client} · {self.sensor_name or self.sensor_id}"
