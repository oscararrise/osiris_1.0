from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0004_add_telemetry_adapter"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Zone",
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
                ("name", models.CharField(max_length=160, verbose_name="nombre")),
                ("code", models.SlugField(max_length=100, verbose_name="código")),
                (
                    "zone_type",
                    models.CharField(
                        choices=[
                            ("farm", "Finca"),
                            ("greenhouse", "Invernadero"),
                            ("sector", "Sector / Zona"),
                            ("cold_room", "Cuarto frío"),
                            ("room", "Cuarto / Sala"),
                            ("field", "Lote / Campo"),
                            ("bed", "Cama / Bancal"),
                            ("other", "Otro"),
                        ],
                        default="sector",
                        max_length=24,
                        verbose_name="tipo de zona",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="activa")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sensor_zones",
                        to="core.client",
                        verbose_name="cliente",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="children",
                        to="sensor_config.zone",
                        verbose_name="zona superior",
                    ),
                ),
            ],
            options={
                "verbose_name": "zona de sensor",
                "verbose_name_plural": "zonas de sensores",
                "ordering": ("client__name", "name"),
                "indexes": [
                    models.Index(
                        fields=["client", "zone_type"],
                        name="sensor_zone_client_type_idx",
                    ),
                    models.Index(
                        fields=["client", "parent"],
                        name="sensor_zone_client_parent_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("client", "code"),
                        name="unique_sensor_zone_code_per_client",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="ClientSensor",
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
                (
                    "external_sensor_id",
                    models.CharField(max_length=160, verbose_name="sensor ID"),
                ),
                (
                    "sensor_name",
                    models.CharField(blank=True, max_length=200, verbose_name="nombre del sensor"),
                ),
                (
                    "sensor_detail",
                    models.CharField(blank=True, max_length=500, verbose_name="sensor detail"),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="activo")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="configured_sensors",
                        to="core.client",
                        verbose_name="cliente",
                    ),
                ),
            ],
            options={
                "verbose_name": "sensor configurado",
                "verbose_name_plural": "sensores configurados",
                "ordering": ("client__name", "sensor_name", "external_sensor_id"),
                "indexes": [
                    models.Index(
                        fields=["client", "external_sensor_id"],
                        name="client_sensor_external_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("client", "external_sensor_id"),
                        name="unique_external_sensor_per_client",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="SensorPlacement",
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
                ("city", models.CharField(blank=True, max_length=120, verbose_name="ciudad")),
                (
                    "department",
                    models.CharField(blank=True, max_length=120, verbose_name="departamento"),
                ),
                (
                    "latitude",
                    models.DecimalField(
                        blank=True,
                        decimal_places=7,
                        max_digits=10,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("-90")),
                            django.core.validators.MaxValueValidator(Decimal("90")),
                        ],
                        verbose_name="latitud",
                    ),
                ),
                (
                    "longitude",
                    models.DecimalField(
                        blank=True,
                        decimal_places=7,
                        max_digits=10,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("-180")),
                            django.core.validators.MaxValueValidator(Decimal("180")),
                        ],
                        verbose_name="longitud",
                    ),
                ),
                (
                    "altitude_m",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=8,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("-1000")),
                            django.core.validators.MaxValueValidator(Decimal("10000")),
                        ],
                        verbose_name="altura (m s. n. m.)",
                    ),
                ),
                ("valid_from", models.DateTimeField(verbose_name="vigente desde")),
                (
                    "valid_until",
                    models.DateTimeField(blank=True, null=True, verbose_name="vigente hasta"),
                ),
                ("notes", models.CharField(blank=True, max_length=500, verbose_name="notas")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sensor_placements_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="creado por",
                    ),
                ),
                (
                    "sensor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="placements",
                        to="sensor_config.clientsensor",
                        verbose_name="sensor",
                    ),
                ),
                (
                    "zone",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sensor_placements",
                        to="sensor_config.zone",
                        verbose_name="zona",
                    ),
                ),
            ],
            options={
                "verbose_name": "ubicación de sensor",
                "verbose_name_plural": "ubicaciones de sensores",
                "ordering": (
                    "sensor__client__name",
                    "sensor__external_sensor_id",
                    "-valid_from",
                ),
                "indexes": [
                    models.Index(
                        fields=["zone", "valid_until"],
                        name="placement_zone_current_idx",
                    ),
                    models.Index(
                        fields=["sensor", "valid_from"],
                        name="placement_sensor_date_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("valid_until__isnull", True)),
                        fields=("sensor",),
                        name="one_current_placement_per_sensor",
                    )
                ],
            },
        ),
    ]
