from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from aplicaciones.core.models import Client


class Zone(models.Model):
    """Hierarchical physical area owned by one client.

    A zone can represent a farm, greenhouse, sector, cold room or any smaller
    operational subdivision. Hierarchy is modeled through ``parent`` so OSIRIS
    is not limited to a fixed number of location levels.
    """

    class ZoneType(models.TextChoices):
        FARM = "farm", "Finca"
        GREENHOUSE = "greenhouse", "Invernadero"
        SECTOR = "sector", "Sector / Zona"
        COLD_ROOM = "cold_room", "Cuarto frío"
        ROOM = "room", "Cuarto / Sala"
        FIELD = "field", "Lote / Campo"
        BED = "bed", "Cama / Bancal"
        OTHER = "other", "Otro"

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="sensor_zones",
        verbose_name="cliente",
    )
    name = models.CharField("nombre", max_length=160)
    code = models.SlugField("código", max_length=100)
    zone_type = models.CharField(
        "tipo de zona",
        max_length=24,
        choices=ZoneType.choices,
        default=ZoneType.SECTOR,
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="zona superior",
    )
    is_active = models.BooleanField("activa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("client__name", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("client", "code"),
                name="unique_sensor_zone_code_per_client",
            )
        ]
        indexes = [
            models.Index(fields=("client", "zone_type"), name="sensor_zone_client_type_idx"),
            models.Index(fields=("client", "parent"), name="sensor_zone_client_parent_idx"),
        ]
        verbose_name = "zona de sensor"
        verbose_name_plural = "zonas de sensores"

    def __str__(self) -> str:
        return f"{self.client} · {self.full_name}"

    @property
    def full_name(self) -> str:
        names = [self.name]
        current = self.parent
        visited: set[int] = set()
        while current is not None:
            if current.pk is not None:
                if current.pk in visited:
                    break
                visited.add(current.pk)
            names.append(current.name)
            current = current.parent
        return " / ".join(reversed(names))

    def clean(self) -> None:
        super().clean()
        if self.parent_id is None:
            return
        if self.pk is not None and self.parent_id == self.pk:
            raise ValidationError({"parent": "Una zona no puede ser su propio padre."})
        if self.client_id is not None and self.parent.client_id != self.client_id:
            raise ValidationError(
                {"parent": "La zona superior debe pertenecer al mismo cliente."}
            )

        current = self.parent
        visited: set[int] = set()
        while current is not None:
            if current.pk is not None:
                if self.pk is not None and current.pk == self.pk:
                    raise ValidationError(
                        {"parent": "La jerarquía de zonas no puede contener ciclos."}
                    )
                if current.pk in visited:
                    raise ValidationError(
                        {"parent": "La jerarquía de zonas no puede contener ciclos."}
                    )
                visited.add(current.pk)
            current = current.parent

    def nearest_facility(self) -> Zone | None:
        """Return the closest farm/greenhouse ancestor, including this zone."""

        current: Zone | None = self
        visited: set[int] = set()
        while current is not None:
            if current.zone_type in {self.ZoneType.FARM, self.ZoneType.GREENHOUSE}:
                return current
            if current.pk is not None:
                if current.pk in visited:
                    break
                visited.add(current.pk)
            current = current.parent
        return None


class ClientSensor(models.Model):
    """OSIRIS-owned metadata for a sensor that lives in an external source."""

    class ActivityType(models.TextChoices):
        CROP = "crop", "Cultivo"
        POULTRY = "poultry", "Avicultura"
        LIVESTOCK = "livestock", "Ganadería"
        AQUACULTURE = "aquaculture", "Acuicultura"
        STORAGE = "storage", "Almacenamiento / cadena de frío"
        OTHER = "other", "Otro"

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="configured_sensors",
        verbose_name="cliente",
    )
    external_sensor_id = models.CharField("sensor ID", max_length=160)
    sensor_name = models.CharField("nombre del sensor", max_length=200, blank=True)
    sensor_detail = models.CharField("sensor detail", max_length=500, blank=True)
    activity_type = models.CharField(
        "actividad",
        max_length=24,
        choices=ActivityType.choices,
        blank=True,
        default="",
        help_text="Contexto productivo local de OSIRIS.",
    )
    product_name = models.CharField(
        "producto / especie",
        max_length=160,
        blank=True,
        help_text="Ej. Arándano, Fresa, Tomate o Gallinas.",
    )
    is_active = models.BooleanField(
        "activo en fuente",
        default=True,
        help_text="Refleja el estado reportado por la fuente externa.",
    )
    dashboard_enabled = models.BooleanField(
        "visible en dashboard",
        default=True,
        help_text="Control local de OSIRIS. No modifica el sensor ni la base externa.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("client__name", "sensor_name", "external_sensor_id")
        constraints = [
            models.UniqueConstraint(
                fields=("client", "external_sensor_id"),
                name="unique_external_sensor_per_client",
            )
        ]
        indexes = [
            models.Index(
                fields=("client", "external_sensor_id"),
                name="client_sensor_external_idx",
            )
        ]
        verbose_name = "sensor configurado"
        verbose_name_plural = "sensores configurados"

    def __str__(self) -> str:
        label = self.sensor_name or self.external_sensor_id
        return f"{self.client} · {label}"

    @property
    def current_placement(self) -> SensorPlacement | None:
        return self.placements.filter(valid_until__isnull=True).select_related("zone").first()

    @property
    def is_dashboard_visible(self) -> bool:
        return self.is_active and self.dashboard_enabled

    @property
    def productive_context(self) -> str:
        activity = self.get_activity_type_display() if self.activity_type else ""
        if activity and self.product_name:
            return f"{activity} · {self.product_name}"
        return activity or self.product_name or "Sin definir"


class SensorPlacement(models.Model):
    """Time-aware physical placement of a sensor.

    Closing a placement instead of overwriting it preserves the physical context
    required to interpret historical Aranet measurements correctly.
    """

    sensor = models.ForeignKey(
        ClientSensor,
        on_delete=models.CASCADE,
        related_name="placements",
        verbose_name="sensor",
    )
    zone = models.ForeignKey(
        Zone,
        on_delete=models.PROTECT,
        related_name="sensor_placements",
        null=True,
        blank=True,
        verbose_name="zona",
    )
    city = models.CharField("ciudad", max_length=120, blank=True)
    department = models.CharField("departamento", max_length=120, blank=True)
    latitude = models.DecimalField(
        "latitud",
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("-90")), MaxValueValidator(Decimal("90"))],
    )
    longitude = models.DecimalField(
        "longitud",
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("-180")), MaxValueValidator(Decimal("180"))],
    )
    altitude_m = models.DecimalField(
        "altura (m s. n. m.)",
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("-1000")),
            MaxValueValidator(Decimal("10000")),
        ],
    )
    valid_from = models.DateTimeField("vigente desde")
    valid_until = models.DateTimeField("vigente hasta", null=True, blank=True)
    notes = models.CharField("notas", max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="sensor_placements_created",
        null=True,
        blank=True,
        verbose_name="creado por",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("sensor__client__name", "sensor__external_sensor_id", "-valid_from")
        constraints = [
            models.UniqueConstraint(
                fields=("sensor",),
                condition=models.Q(valid_until__isnull=True),
                name="one_current_placement_per_sensor",
            )
        ]
        indexes = [
            models.Index(fields=("zone", "valid_until"), name="placement_zone_current_idx"),
            models.Index(fields=("sensor", "valid_from"), name="placement_sensor_date_idx"),
        ]
        verbose_name = "ubicación de sensor"
        verbose_name_plural = "ubicaciones de sensores"

    def __str__(self) -> str:
        location = self.zone.full_name if self.zone_id else self.city or "Sin zona"
        return f"{self.sensor} · {location}"

    @property
    def is_current(self) -> bool:
        return self.valid_until is None

    @property
    def farm_or_greenhouse(self) -> Zone | None:
        if self.zone_id is None:
            return None
        return self.zone.nearest_facility()

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        if self.zone_id is not None and self.sensor_id is not None:
            if self.zone.client_id != self.sensor.client_id:
                errors["zone"] = "La zona debe pertenecer al mismo cliente que el sensor."

        if (self.latitude is None) != (self.longitude is None):
            message = "Latitud y longitud deben registrarse juntas."
            errors["latitude"] = message
            errors["longitude"] = message

        if self.valid_until is not None and self.valid_until <= self.valid_from:
            errors["valid_until"] = "La fecha final debe ser posterior a la fecha inicial."

        if errors:
            raise ValidationError(errors)
