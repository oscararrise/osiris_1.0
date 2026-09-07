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
    email_recipients = models.CharField(
        "destinatarios email",
        max_length=500,
        blank=True,
    )
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
    requires_confirmation = models.BooleanField(
        "requiere confirmación humana",
        default=True,
    )
    ai_instruction = models.TextField(
        "instrucción para la IA",
        max_length=2500,
        blank=True,
        help_text=(
            "Contexto operativo que la IA debe considerar antes de proponer "
            "o ejecutar acciones."
        ),
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


class AgronomicVariableRelationship(models.Model):
    """OSIRIS-owned relationship between several sensor variables and a crop goal."""

    class RelationshipType(models.TextChoices):
        CLIMATE = "climate", "Clima y transpiración"
        ROOT_ZONE = "root_zone", "Zona radicular / fertirriego"
        PHOTOSYNTHESIS = "photosynthesis", "Fotosíntesis y crecimiento"
        DISEASE_RISK = "disease_risk", "Riesgo sanitario"
        CUSTOM = "custom", "Personalizada"

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="agronomic_variable_relationships",
        verbose_name="cliente",
    )
    sensor_id = models.CharField("sensor externo", max_length=160)
    sensor_name = models.CharField("nombre del sensor", max_length=200, blank=True)
    crop_name = models.CharField("cultivo", max_length=160)
    name = models.CharField("nombre de la relación", max_length=200)
    relationship_type = models.CharField(
        "tipo de relación",
        max_length=32,
        choices=RelationshipType.choices,
        default=RelationshipType.CUSTOM,
    )
    variable_ids = models.JSONField("IDs de variables", default=list)
    variable_names = models.JSONField("nombres de variables", default=list)
    agronomic_goal = models.CharField(
        "objetivo agronómico",
        max_length=500,
        blank=True,
    )
    expert_guidance = models.TextField(
        "interpretación agronómica",
        max_length=2500,
        blank=True,
    )
    is_enabled = models.BooleanField("activa", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_agronomic_relationships",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("client", "sensor_id", "name"),
                name="unique_agronomic_relationship_name_per_sensor",
            )
        ]
        ordering = ("client__name", "crop_name", "sensor_name", "name")
        verbose_name = "relación agronómica de variables"
        verbose_name_plural = "relaciones agronómicas de variables"

    def __str__(self) -> str:
        return f"{self.client} · {self.crop_name} · {self.name}"


class AgronomicRelationshipAlert(models.Model):
    """Two-variable alert rule attached to an agronomic relationship."""

    class Logic(models.TextChoices):
        AND = "and", "Y (AND)"
        OR = "or", "O (OR)"

    class Operator(models.TextChoices):
        GREATER_THAN = "gt", "Mayor que"
        GREATER_EQUAL = "gte", "Mayor o igual que"
        LESS_THAN = "lt", "Menor que"
        LESS_EQUAL = "lte", "Menor o igual que"

    class Severity(models.TextChoices):
        LOW = "low", "Baja"
        MEDIUM = "medium", "Media"
        HIGH = "high", "Alta"
        CRITICAL = "critical", "Crítica"

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="agronomic_relationship_alerts",
        verbose_name="cliente",
    )
    relationship = models.ForeignKey(
        AgronomicVariableRelationship,
        on_delete=models.CASCADE,
        related_name="alerts",
        verbose_name="relación agronómica",
    )
    name = models.CharField("nombre", max_length=200)
    variable_a_key = models.CharField("variable A", max_length=320)
    operator_a = models.CharField(
        "operador A",
        max_length=8,
        choices=Operator.choices,
        default=Operator.GREATER_THAN,
    )
    threshold_a = models.FloatField("umbral A")
    variable_b_key = models.CharField("variable B", max_length=320)
    operator_b = models.CharField(
        "operador B",
        max_length=8,
        choices=Operator.choices,
        default=Operator.GREATER_THAN,
    )
    threshold_b = models.FloatField("umbral B")
    logic = models.CharField("lógica", max_length=8, choices=Logic.choices, default=Logic.AND)
    duration_minutes = models.PositiveIntegerField("duración mínima (min)", default=10)
    cooldown_minutes = models.PositiveIntegerField("cooldown (min)", default=30)
    severity = models.CharField(
        "severidad",
        max_length=12,
        choices=Severity.choices,
        default=Severity.MEDIUM,
    )
    email_enabled = models.BooleanField("notificar por email", default=False)
    email_recipients = models.CharField("destinatarios email", max_length=500, blank=True)
    whatsapp_enabled = models.BooleanField("notificar por WhatsApp", default=False)
    whatsapp_recipients = models.CharField(
        "destinatarios WhatsApp", max_length=500, blank=True
    )
    is_enabled = models.BooleanField("activa", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_agronomic_relationship_alerts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("relationship", "name"),
                name="unique_alert_name_per_agronomic_relationship",
            )
        ]
        ordering = ("relationship__name", "-is_enabled", "name")
        verbose_name = "alerta de relación agronómica"
        verbose_name_plural = "alertas de relaciones agronómicas"

    def __str__(self) -> str:
        return f"{self.relationship} · {self.name}"
