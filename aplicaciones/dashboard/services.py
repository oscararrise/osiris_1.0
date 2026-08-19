from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from datetime import datetime, timedelta
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


def _percent_delta(current: float | int | None, previous: float | int | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return ((float(current) - float(previous)) / abs(float(previous))) * 100


def _series_statistics(series: list[dict[str, Any]]) -> dict[str, Any]:
    valid_points = [
        point
        for point in series
        if point.get("value") is not None and math.isfinite(float(point["value"]))
    ]
    sample_count = sum(int(point.get("sample_count") or 1) for point in valid_points)
    weighted_total = sum(
        float(point["value"]) * int(point.get("sample_count") or 1)
        for point in valid_points
    )
    average = weighted_total / sample_count if sample_count else None

    standard_deviation = None
    coefficient_variation = None
    if average is not None and sample_count:
        variance = sum(
            int(point.get("sample_count") or 1) * (float(point["value"]) - average) ** 2
            for point in valid_points
        ) / sample_count
        standard_deviation = math.sqrt(max(variance, 0))
        if average != 0:
            coefficient_variation = abs(standard_deviation / average) * 100

    first_value = float(valid_points[0]["value"]) if valid_points else None
    last_value = float(valid_points[-1]["value"]) if valid_points else None
    period_change = (
        last_value - first_value
        if first_value is not None and last_value is not None
        else None
    )
    period_change_pct = _percent_delta(last_value, first_value)

    return {
        "minimum": min(
            (float(point.get("minimum", point["value"])) for point in valid_points),
            default=None,
        ),
        "maximum": max(
            (float(point.get("maximum", point["value"])) for point in valid_points),
            default=None,
        ),
        "average": average,
        "points": len(valid_points),
        "samples": sample_count,
        "standard_deviation": standard_deviation,
        "coefficient_variation": coefficient_variation,
        "first_value": first_value,
        "last_value": last_value,
        "period_change": period_change,
        "period_change_pct": period_change_pct,
    }


def _normalise_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _fleet_analytics(
    sensors: list[dict[str, Any]],
    now: datetime,
    freshness_minutes: int,
) -> dict[str, Any]:
    sensor_health: list[dict[str, Any]] = []
    online = 0
    delayed = 0
    offline = 0
    rssi_values: list[float] = []

    for sensor in sensors:
        last_seen = _normalise_datetime(sensor.get("last_seen_at"))
        age_minutes = None
        if last_seen is not None:
            age_minutes = max((now - last_seen).total_seconds() / 60, 0)

        if age_minutes is not None and age_minutes <= freshness_minutes:
            status = "online"
            status_label = "En línea"
            online += 1
        elif age_minutes is not None and age_minutes <= freshness_minutes * 4:
            status = "delayed"
            status_label = "Con retraso"
            delayed += 1
        else:
            status = "offline"
            status_label = "Sin telemetría"
            offline += 1

        rssi = sensor.get("rssi_dbm")
        if rssi is not None:
            try:
                numeric_rssi = float(rssi)
            except (TypeError, ValueError):
                numeric_rssi = None
            if numeric_rssi is not None and math.isfinite(numeric_rssi):
                rssi_values.append(numeric_rssi)

        sensor_health.append(
            {
                **sensor,
                "health_status": status,
                "health_label": status_label,
                "age_minutes": age_minutes,
            }
        )

    sensor_health.sort(
        key=lambda sensor: (
            {"offline": 0, "delayed": 1, "online": 2}.get(sensor["health_status"], 3),
            -(sensor.get("age_minutes") or 0),
        )
    )
    total = len(sensors)
    return {
        "total": total,
        "online": online,
        "delayed": delayed,
        "offline": offline,
        "availability_pct": (online / total * 100) if total else 0,
        "average_rssi": sum(rssi_values) / len(rssi_values) if rssi_values else None,
        "rssi_samples": len(rssi_values),
        "freshness_minutes": freshness_minutes,
        "sensors": sensor_health,
    }


def _executive_insights(
    current: dict[str, Any],
    previous: dict[str, Any],
    fleet: dict[str, Any],
    fleet_alarms: list[dict[str, Any]],
    metric_name: str,
) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []

    availability = float(fleet.get("availability_pct") or 0)
    if availability >= 90:
        insights.append(
            {
                "tone": "positive",
                "title": "Cobertura operativa sólida",
                "text": (
                    f"{fleet['online']} de {fleet['total']} sensores están reportando dentro "
                    f"de la ventana de {fleet['freshness_minutes']} minutos."
                ),
            }
        )
    elif availability >= 70:
        insights.append(
            {
                "tone": "attention",
                "title": "Cobertura con oportunidades",
                "text": (
                    f"La disponibilidad reciente es {availability:.1f}%. Conviene revisar los "
                    f"{fleet['delayed'] + fleet['offline']} sensores con retraso o sin telemetría."
                ),
            }
        )
    else:
        insights.append(
            {
                "tone": "risk",
                "title": "Cobertura de datos reducida",
                "text": (
                    f"Solo {availability:.1f}% de la flota está reportando recientemente. "
                    "La lectura agregada puede no representar toda la operación."
                ),
            }
        )

    average_delta = _percent_delta(current.get("average"), previous.get("average"))
    if average_delta is not None:
        if abs(average_delta) < 3:
            insights.append(
                {
                    "tone": "neutral",
                    "title": f"{metric_name} estable frente al periodo anterior",
                    "text": (
                        f"El promedio varió {average_delta:+.1f}%, un cambio pequeño entre "
                        "periodos equivalentes."
                    ),
                }
            )
        else:
            direction = "por encima" if average_delta > 0 else "por debajo"
            insights.append(
                {
                    "tone": "attention" if abs(average_delta) >= 15 else "neutral",
                    "title": f"Cambio de nivel en {metric_name}",
                    "text": (
                        f"El promedio actual está {abs(average_delta):.1f}% {direction} del "
                        "periodo inmediatamente anterior."
                    ),
                }
            )

    sample_delta = _percent_delta(current.get("samples"), previous.get("samples"))
    if sample_delta is not None and sample_delta <= -20:
        insights.append(
            {
                "tone": "attention",
                "title": "Menor volumen de observaciones",
                "text": (
                    f"El periodo actual contiene {abs(sample_delta):.1f}% menos muestras. "
                    "Revise continuidad de transmisión antes de interpretar cambios pequeños."
                ),
            }
        )

    variability = current.get("coefficient_variation")
    if variability is not None and variability >= 20:
        insights.append(
            {
                "tone": "attention",
                "title": f"Variabilidad elevada en {metric_name}",
                "text": (
                    f"La dispersión relativa es {variability:.1f}% del promedio. La serie "
                    "presenta oscilaciones relevantes dentro del periodo."
                ),
            }
        )

    if fleet_alarms:
        insights.append(
            {
                "tone": "risk",
                "title": "Alertas que requieren atención",
                "text": (
                    f"Hay {len(fleet_alarms)} alerta(s) activa(s) en la flota. Priorice las "
                    "de mayor severidad antes de evaluar desempeño agregado."
                ),
            }
        )
    else:
        insights.append(
            {
                "tone": "positive",
                "title": "Sin alertas activas",
                "text": "No se observan reglas de alarma activas en los sensores de la flota.",
            }
        )

    return insights[:4]


def _comparison_rows(
    current: dict[str, Any],
    previous: dict[str, Any],
) -> list[dict[str, Any]]:
    definitions = (
        ("Promedio", "average"),
        ("Mínimo", "minimum"),
        ("Máximo", "maximum"),
        ("Muestras", "samples"),
    )
    rows = []
    for label, key in definitions:
        current_value = current.get(key)
        previous_value = previous.get(key)
        rows.append(
            {
                "label": label,
                "current": current_value,
                "previous": previous_value,
                "delta_pct": _percent_delta(current_value, previous_value),
                "is_count": key == "samples",
            }
        )
    return rows


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
            "executive": None,
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
    duration = RANGES[range_key][1]
    start = end - duration

    latest_values = _cached(
        _cache_key(client, source, "latest", selected_sensor_id),
        lambda: adapter.latest_values(selected_sensor_id),
    )
    alarms = _cached(
        _cache_key(client, source, "alarms", selected_sensor_id),
        lambda: adapter.active_alarms(selected_sensor_id),
        timeout=min(settings.DASHBOARD_CACHE_TTL, 60),
    )
    series: list[dict[str, Any]] = []
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

    statistics = _series_statistics(series)
    executive = None

    if (
        client.slug == "vladimir"
        and source.adapter_key == ClientDataSource.Adapter.ARANET
        and selected_metric is not None
    ):
        previous_end = start
        previous_start = previous_end - duration
        previous_series = _cached(
            _cache_key(
                client,
                source,
                "previous-series",
                selected_sensor_id,
                selected_metric_id,
                selected_probe_no,
                range_key,
                previous_end.replace(second=0, microsecond=0).isoformat(),
            ),
            lambda: adapter.time_series(
                selected_sensor_id,
                selected_metric_id,
                selected_probe_no,
                previous_start,
                previous_end,
                settings.DASHBOARD_MAX_POINTS,
            ),
        )
        previous_statistics = _series_statistics(previous_series)
        freshness_minutes = int(source.settings.get("freshness_minutes", 180))
        fleet = _fleet_analytics(sensors, end, max(freshness_minutes, 1))
        fleet_alarms = _cached(
            _cache_key(client, source, "fleet-alarms"),
            lambda: adapter.active_alarms(None),
            timeout=min(settings.DASHBOARD_CACHE_TTL, 60),
        )
        average_delta_pct = _percent_delta(
            statistics.get("average"), previous_statistics.get("average")
        )
        sample_delta_pct = _percent_delta(
            statistics.get("samples"), previous_statistics.get("samples")
        )
        selected_health = next(
            (
                sensor
                for sensor in fleet["sensors"]
                if str(sensor["id"]) == selected_sensor_id
            ),
            None,
        )
        executive = {
            "previous_series": previous_series,
            "previous_statistics": previous_statistics,
            "previous_start": previous_start,
            "previous_end": previous_end,
            "average_delta_pct": average_delta_pct,
            "sample_delta_pct": sample_delta_pct,
            "fleet": fleet,
            "fleet_alarms": fleet_alarms,
            "selected_health": selected_health,
            "comparison_rows": _comparison_rows(statistics, previous_statistics),
            "insights": _executive_insights(
                statistics,
                previous_statistics,
                fleet,
                fleet_alarms,
                str(selected_metric.get("name") or selected_metric_id),
            ),
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
        "executive": executive,
    }
