"""
Helpers de rendimiento para el dashboard de telemetría (s2).

El alias de base de datos se mantiene en un ContextVar por request para que
clientes distintos puedan reutilizar las vistas legacy sin compartir conexión
ni caché accidentalmente.
"""

from contextvars import ContextVar

from django.conf import settings
from django.core.cache import cache

from .models import SensorReading


_telemetry_database_alias = ContextVar(
    "osiris_telemetry_database_alias",
    default="telemetry",
)


def set_telemetry_database_alias(database_alias):
    return _telemetry_database_alias.set(database_alias)


def reset_telemetry_database_alias(token):
    _telemetry_database_alias.reset(token)


def get_telemetry_database_alias():
    return _telemetry_database_alias.get()


def telemetry_queryset():
    return SensorReading.objects.using(get_telemetry_database_alias())


def get_cache_ttl(name, default):
    return getattr(settings, name, default)


def downsample_readings(readings, max_points):
    """
    Reduce puntos para gráficos/tabla sin perder extremos.
    """
    total = len(readings)

    if total <= max_points or max_points < 2:
        return readings

    step = (total - 1) / (max_points - 1)
    indices = {
        0,
        total - 1,
    }

    for index in range(max_points):
        indices.add(int(round(index * step)))

    return [
        readings[index]
        for index in sorted(indices)
    ]


def get_telemetry_devices(force_refresh=False):
    database_alias = get_telemetry_database_alias()
    cache_key = f"telemetry:{database_alias}:devices:v2"
    ttl = get_cache_ttl(
        "TELEMETRY_DEVICES_CACHE_TTL",
        300,
    )

    if not force_refresh:
        cached = cache.get(cache_key)

        if cached is not None:
            return cached

    devices = list(
        telemetry_queryset()
        .order_by("device_id")
        .values_list("device_id", flat=True)
        .distinct()
    )

    cache.set(cache_key, devices, ttl)
    return devices


def get_latest_device_id(force_refresh=False):
    database_alias = get_telemetry_database_alias()
    cache_key = f"telemetry:{database_alias}:latest_device:v2"
    ttl = get_cache_ttl(
        "TELEMETRY_DEVICES_CACHE_TTL",
        300,
    )

    if not force_refresh:
        cached = cache.get(cache_key)

        if cached is not None:
            return cached

    latest = (
        telemetry_queryset()
        .order_by("-received_at")
        .values_list("device_id", flat=True)
        .first()
    )

    cache.set(cache_key, latest, ttl)
    return latest


def build_dashboard_cache_key(
    device_id,
    date_from,
    date_to,
    range_key,
):
    database_alias = get_telemetry_database_alias()
    return (
        "telemetry:dashboard:v3:"
        f"{database_alias}:{device_id}:{date_from}:{date_to}:{range_key}"
    )
