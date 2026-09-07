from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

alias_validator = RegexValidator(
    regex=r"^[a-z][a-z0-9_]{1,62}$",
    message="Use entre 2 y 63 caracteres: letras minúsculas, números y guion bajo.",
)
color_validator = RegexValidator(
    regex=r"^#[0-9a-fA-F]{6}$",
    message="Use un color hexadecimal como #176247.",
)


class AccessLevel(models.IntegerChoices):
    VIEWER = 10, "Consulta"
    OPERATOR = 20, "Operador"
    CLIENT_ADMIN = 30, "Administrador del cliente"


class Client(models.Model):
    name = models.CharField("nombre", max_length=160, unique=True)
    slug = models.SlugField("identificador", max_length=80, unique=True)
    is_active = models.BooleanField("activo", default=True)
    primary_color = models.CharField(
        "color principal", max_length=7, default="#176247", validators=[color_validator]
    )
    timezone = models.CharField("zona horaria", max_length=64, default="America/Bogota")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "cliente"
        verbose_name_plural = "clientes"

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValidationError({"timezone": "La zona horaria no es válida."}) from exc


class ClientDataSource(models.Model):
    class Adapter(models.TextChoices):
        ARANET = "aranet", "Aranet PostgreSQL"
        TELEMETRY = "telemetry", "Telemetría agrícola PostgreSQL"

    client = models.OneToOneField(
        Client,
        on_delete=models.CASCADE,
        related_name="data_source",
        verbose_name="cliente",
    )
    name = models.CharField("nombre", max_length=120, default="Base de sensores")
    database_alias = models.CharField(
        "alias de conexión", max_length=63, unique=True, validators=[alias_validator]
    )
    adapter_key = models.CharField(
        "adaptador", max_length=40, choices=Adapter.choices, default=Adapter.ARANET
    )
    settings = models.JSONField(
        "configuración no secreta",
        default=dict,
        blank=True,
        help_text="Opciones del adaptador. Nunca guarde contraseñas aquí.",
    )
    is_active = models.BooleanField("activa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "fuente de datos"
        verbose_name_plural = "fuentes de datos"

    def __str__(self) -> str:
        return f"{self.client} · {self.name}"

    def clean(self) -> None:
        super().clean()
        if self.database_alias == "default":
            raise ValidationError(
                {"database_alias": "La base central no puede usarse como fuente de sensores."}
            )
        if not isinstance(self.settings, dict):
            raise ValidationError({"settings": "La configuración debe ser un objeto JSON."})
        forbidden_keys = {
            "api_key",
            "database",
            "dsn",
            "host",
            "name",
            "password",
            "port",
            "secret",
            "token",
            "user",
            "username",
        }
        invalid_keys = forbidden_keys.intersection(str(key).casefold() for key in self.settings)
        if invalid_keys:
            raise ValidationError(
                {
                    "settings": (
                        "Las credenciales y datos de conexión deben vivir en el archivo "
                        f"protegido. Claves no permitidas: {', '.join(sorted(invalid_keys))}."
                    )
                }
            )


class ClientMembership(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="client_membership",
        verbose_name="usuario",
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="memberships",
        verbose_name="cliente",
    )
    access_level = models.PositiveSmallIntegerField(
        "nivel de acceso", choices=AccessLevel.choices, default=AccessLevel.VIEWER
    )
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("client__name", "user__username")
        verbose_name = "membresía"
        verbose_name_plural = "membresías"

    def __str__(self) -> str:
        return f"{self.user} · {self.client}"


class PlatformModule(models.Model):
    code = models.SlugField("código", max_length=50, unique=True)
    name = models.CharField("nombre", max_length=100)
    description = models.CharField("descripción", max_length=240, blank=True)
    route_name = models.CharField("nombre de ruta", max_length=80)
    icon = models.CharField("icono", max_length=80, default="fa-solid fa-grid-2")
    category = models.CharField("categoría", max_length=80, default="Operación")
    sort_order = models.PositiveSmallIntegerField("orden", default=100)
    is_active = models.BooleanField("activo", default=True)

    class Meta:
        ordering = ("sort_order", "name")
        verbose_name = "módulo de plataforma"
        verbose_name_plural = "módulos de plataforma"

    def __str__(self) -> str:
        return self.name


class ClientModule(models.Model):
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="module_settings",
        verbose_name="cliente",
    )
    module = models.ForeignKey(
        PlatformModule,
        on_delete=models.CASCADE,
        related_name="client_settings",
        verbose_name="módulo",
    )
    is_enabled = models.BooleanField("visible", default=True)
    minimum_access_level = models.PositiveSmallIntegerField(
        "acceso mínimo", choices=AccessLevel.choices, default=AccessLevel.VIEWER
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("client", "module"),
                name="unique_module_configuration_per_client",
            )
        ]
        ordering = ("module__sort_order",)
        verbose_name = "módulo habilitado"
        verbose_name_plural = "módulos habilitados"

    def __str__(self) -> str:
        return f"{self.client} · {self.module}"


class ControlEvent(models.Model):
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="control_events", verbose_name="cliente"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="control_events",
        verbose_name="creado por",
    )
    payload = models.JSONField("datos de control", default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "evento de control"
        verbose_name_plural = "eventos de control"

    def __str__(self) -> str:
        return f"{self.client} · {self.created_at:%Y-%m-%d %H:%M}"


class SupportRequest(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Abierta"
        IN_PROGRESS = "in_progress", "En proceso"
        RESOLVED = "resolved", "Resuelta"

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="support_requests",
        verbose_name="cliente",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_requests",
        verbose_name="creada por",
    )
    request_type = models.CharField("tipo", max_length=80, default="Solicitud")
    description = models.TextField("descripción", max_length=4000)
    status = models.CharField("estado", max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "solicitud de soporte"
        verbose_name_plural = "solicitudes de soporte"

    def __str__(self) -> str:
        return f"{self.client} · {self.request_type}"
