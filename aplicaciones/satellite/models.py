from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from aplicaciones.core.models import Client


def validate_polygon_geojson(value: object) -> None:
    """Validate the small GeoJSON subset accepted by the satellite module."""

    if not isinstance(value, dict):
        raise ValidationError("La geometría debe ser un objeto GeoJSON.")
    if value.get("type") != "Polygon":
        raise ValidationError("La geometría debe ser un GeoJSON Polygon.")

    coordinates = value.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise ValidationError("El Polygon debe contener al menos un anillo de coordenadas.")

    outer_ring = coordinates[0]
    if not isinstance(outer_ring, list) or len(outer_ring) < 4:
        raise ValidationError("El anillo exterior debe contener al menos cuatro puntos.")

    normalized_points: list[tuple[float, float]] = []
    for point in outer_ring:
        if not isinstance(point, list | tuple) or len(point) < 2:
            raise ValidationError("Cada punto debe contener longitud y latitud.")
        longitude, latitude = point[0], point[1]
        if isinstance(longitude, bool) or isinstance(latitude, bool):
            raise ValidationError("Longitud y latitud deben ser valores numéricos.")
        if not isinstance(longitude, int | float) or not isinstance(latitude, int | float):
            raise ValidationError("Longitud y latitud deben ser valores numéricos.")
        if not -180 <= longitude <= 180:
            raise ValidationError("La longitud debe estar entre -180 y 180.")
        if not -90 <= latitude <= 90:
            raise ValidationError("La latitud debe estar entre -90 y 90.")
        normalized_points.append((float(longitude), float(latitude)))

    if normalized_points[0] != normalized_points[-1]:
        raise ValidationError("El anillo exterior del Polygon debe estar cerrado.")


class SatelliteField(models.Model):
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="satellite_fields",
        verbose_name="cliente",
    )
    name = models.CharField("nombre", max_length=160)
    geometry = models.JSONField(
        "geometría",
        validators=[validate_polygon_geojson],
        help_text="GeoJSON Polygon en coordenadas WGS84 (longitud, latitud).",
    )
    eosda_field_id = models.PositiveBigIntegerField("EOSDA field id", null=True, blank=True)
    area_ha = models.DecimalField(
        "área (ha)", max_digits=12, decimal_places=4, null=True, blank=True
    )
    crop_type = models.CharField("cultivo", max_length=120, blank=True)
    sowing_date = models.DateField("fecha de siembra", null=True, blank=True)
    is_active = models.BooleanField("activo", default=True)
    last_sync_at = models.DateTimeField("última sincronización", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("client__name", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("client", "name"),
                name="unique_satellite_field_name_per_client",
            ),
            models.UniqueConstraint(
                fields=("client", "eosda_field_id"),
                name="unique_eosda_field_per_client",
            ),
        ]
        verbose_name = "lote satelital"
        verbose_name_plural = "lotes satelitales"

    def __str__(self) -> str:
        return f"{self.client} · {self.name}"


class SatelliteScene(models.Model):
    class Provider(models.TextChoices):
        EOSDA = "eosda", "EOSDA"

    field = models.ForeignKey(
        SatelliteField,
        on_delete=models.CASCADE,
        related_name="scenes",
        verbose_name="lote",
    )
    provider = models.CharField(
        "proveedor", max_length=20, choices=Provider.choices, default=Provider.EOSDA
    )
    dataset = models.CharField("dataset", max_length=80, default="sentinel2l2a")
    view_id = models.CharField("view id", max_length=255)
    captured_at = models.DateTimeField("fecha de captura")
    cloud_cover = models.FloatField("nubosidad (%)", null=True, blank=True)
    metadata = models.JSONField("metadatos", default=dict, blank=True)
    assets = models.JSONField("archivos", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-captured_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("field", "dataset", "view_id"),
                name="unique_satellite_scene_per_field",
            )
        ]
        indexes = [
            models.Index(fields=("field", "-captured_at"), name="sat_scene_field_date_idx"),
        ]
        verbose_name = "escena satelital"
        verbose_name_plural = "escenas satelitales"

    def __str__(self) -> str:
        return f"{self.field} · {self.captured_at:%Y-%m-%d}"


class SatelliteMeasurement(models.Model):
    scene = models.ForeignKey(
        SatelliteScene,
        on_delete=models.CASCADE,
        related_name="measurements",
        verbose_name="escena",
    )
    index_name = models.CharField("índice", max_length=32)
    average = models.FloatField("promedio", null=True, blank=True)
    minimum = models.FloatField("mínimo", null=True, blank=True)
    maximum = models.FloatField("máximo", null=True, blank=True)
    median = models.FloatField("mediana", null=True, blank=True)
    p10 = models.FloatField("percentil 10", null=True, blank=True)
    p90 = models.FloatField("percentil 90", null=True, blank=True)
    stddev = models.FloatField("desviación estándar", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("scene__captured_at", "index_name")
        constraints = [
            models.UniqueConstraint(
                fields=("scene", "index_name"),
                name="unique_satellite_measurement_per_scene",
            )
        ]
        indexes = [
            models.Index(fields=("index_name",), name="sat_measure_index_idx"),
        ]
        verbose_name = "medición satelital"
        verbose_name_plural = "mediciones satelitales"

    def __str__(self) -> str:
        return f"{self.scene} · {self.index_name}"


class SatelliteJob(models.Model):
    class JobType(models.TextChoices):
        INITIAL_SYNC = "initial_sync", "Sincronización inicial"
        SCENE_SEARCH = "scene_search", "Búsqueda de escenas"
        STATISTICS = "statistics", "Estadísticas"
        IMAGERY = "imagery", "Imágenes"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        RUNNING = "running", "Ejecutando"
        WAITING_PROVIDER = "waiting_provider", "Esperando proveedor"
        COMPLETED = "completed", "Completado"
        FAILED = "failed", "Fallido"

    field = models.ForeignKey(
        SatelliteField,
        on_delete=models.CASCADE,
        related_name="jobs",
        verbose_name="lote",
    )
    scene = models.ForeignKey(
        SatelliteScene,
        on_delete=models.CASCADE,
        related_name="jobs",
        verbose_name="escena",
        null=True,
        blank=True,
    )
    job_type = models.CharField("tipo", max_length=30, choices=JobType.choices)
    status = models.CharField(
        "estado", max_length=30, choices=Status.choices, default=Status.PENDING
    )
    provider_task_id = models.CharField("task id del proveedor", max_length=255, blank=True)
    attempts = models.PositiveSmallIntegerField("intentos", default=0)
    next_check_at = models.DateTimeField("próxima consulta", null=True, blank=True)
    request_payload = models.JSONField("solicitud", default=dict, blank=True)
    result_payload = models.JSONField("resultado", default=dict, blank=True)
    error_message = models.TextField("error", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField("inicio", null=True, blank=True)
    finished_at = models.DateTimeField("fin", null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=("status", "next_check_at"), name="sat_job_status_next_idx"),
            models.Index(fields=("field", "status"), name="sat_job_field_status_idx"),
        ]
        verbose_name = "trabajo satelital"
        verbose_name_plural = "trabajos satelitales"

    def __str__(self) -> str:
        return f"{self.field} · {self.job_type} · {self.status}"

    def clean(self) -> None:
        super().clean()
        if self.scene_id and self.field_id and self.scene.field_id != self.field_id:
            raise ValidationError({"scene": "La escena debe pertenecer al mismo lote del trabajo."})
