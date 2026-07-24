"""
Helpers de rendimiento para el dashboard de telemetría (s2).
"""

from django.conf import settings
from django.core.cache import cache

from .models import SensorReading


def telemetry_queryset():
    return SensorReading.objects.using("telemetry")


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
    cache_key = "telemetry:devices:v1"
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
    cache_key = "telemetry:latest_device:v1"
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
    return (
        "telemetry:dashboard:v2:"
        f"{device_id}:{date_from}:{date_to}:{range_key}"
    )
