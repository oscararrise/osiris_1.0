from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from aplicaciones.core.models import Client, ClientDataSource

from .adapters import get_adapter

RANGES = {
    "24h": ("Últimas 24 horas", timedelta(hours=24)),
    "7d": ("Últimos 7 días", timedelta(days=7)),
    "30d": ("Últimos 30 días", timedelta(days=30)),
    "90d": ("Últimos 90 días", timedelta(days=90)),
}


def _cache_key(client: Client, source: ClientDataSource, section: str, *parts: object) -> str:
    identity = "|".join(str(part) for part in (client.pk, source.pk, section, *parts))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"osiris:dashboard:{digest}"


def _cached(key: str, loader: Callable[[], Any], timeout: int | None = None):
    value = cache.get(key)
    if value is None:
        value = loader()
        cache.set(key, value, timeout or settings.DASHBOARD_CACHE_TTL)
    return value


def build_dashboard(client: Client, query: dict[str, str]) -> dict[str, Any]:
    source = client.data_source
    adapter = get_adapter(source)
    sensors = _cached(
        _cache_key(client, source, "sensors"),
        adapter.list_sensors,
        timeout=max(settings.DASHBOARD_CACHE_TTL, 300),
    )
    if not sensors:
        return {
            "source": source,
            "sensors": [],
            "metrics": [],
            "latest_values": [],
            "alarms": [],
            "series": [],
            "ranges": RANGES,
            "selected_range": "24h",
        }

    sensor_ids = {str(sensor["id"]) for sensor in sensors}
    selected_sensor_id = query.get("sensor", "")
    if selected_sensor_id not in sensor_ids:
        selected_sensor_id = str(sensors[0]["id"])
    selected_sensor = next(sensor for sensor in sensors if str(sensor["id"]) == selected_sensor_id)

    metrics = _cached(
        _cache_key(client, source, "metrics", selected_sensor_id),
        lambda: adapter.list_metrics(selected_sensor_id),
        timeout=max(settings.DASHBOARD_CACHE_TTL, 300),
    )
    metric_keys = {(str(metric["id"]), int(metric["probe_no"])) for metric in metrics}
    selected_metric_id = query.get("metric", "")
    try:
        selected_probe_no = int(query.get("probe", "0"))
    except (TypeError, ValueError):
        selected_probe_no = 0
    if (selected_metric_id, selected_probe_no) not in metric_keys and metrics:
        selected_metric_id = str(metrics[0]["id"])
        selected_probe_no = int(metrics[0]["probe_no"])
    selected_metric = next(
        (
            metric
            for metric in metrics
            if str(metric["id"]) == selected_metric_id
            and int(metric["probe_no"]) == selected_probe_no
        ),
        None,
    )

    range_key = query.get("range", source.settings.get("default_range", "24h"))
    if range_key not in RANGES:
        range_key = "24h"
    end = timezone.now()
    start = end - RANGES[range_key][1]

    latest_values = _cached(
        _cache_key(client, source, "latest", selected_sensor_id),
        lambda: adapter.latest_values(selected_sensor_id),
    )
    alarms = _cached(
        _cache_key(client, source, "alarms", selected_sensor_id),
        lambda: adapter.active_alarms(selected_sensor_id),
        timeout=min(settings.DASHBOARD_CACHE_TTL, 60),
    )
    series = []
    if selected_metric is not None:
        series = _cached(
            _cache_key(
                client,
                source,
                "series",
                selected_sensor_id,
                selected_metric_id,
                selected_probe_no,
                range_key,
                end.replace(second=0, microsecond=0).isoformat(),
            ),
            lambda: adapter.time_series(
                selected_sensor_id,
                selected_metric_id,
                selected_probe_no,
                start,
                end,
                settings.DASHBOARD_MAX_POINTS,
            ),
        )

    valid_points = [point for point in series if point.get("value") is not None]
    sample_count = sum(int(point.get("sample_count") or 1) for point in valid_points)
    weighted_total = sum(
        point["value"] * int(point.get("sample_count") or 1) for point in valid_points
    )
    statistics = {
        "minimum": min(
            (point.get("minimum", point["value"]) for point in valid_points), default=None
        ),
        "maximum": max(
            (point.get("maximum", point["value"]) for point in valid_points), default=None
        ),
        "average": weighted_total / sample_count if sample_count else None,
        "points": len(valid_points),
        "samples": sample_count,
    }
    return {
        "source": source,
        "sensors": sensors,
        "selected_sensor": selected_sensor,
        "selected_sensor_id": selected_sensor_id,
        "metrics": metrics,
        "selected_metric": selected_metric,
        "selected_metric_id": selected_metric_id,
        "selected_probe_no": selected_probe_no,
        "latest_values": latest_values,
        "alarms": alarms,
        "series": series,
        "statistics": statistics,
        "ranges": RANGES,
        "selected_range": range_key,
        "period_start": start,
        "period_end": end,
    }
