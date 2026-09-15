from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from aplicaciones.core.models import Client
from aplicaciones.sensor_config.models import ClientSensor

from .vladimir_overview import _analysis_insights, _safe_float


def _filtered_health(
    sensors: list[dict[str, Any]],
    previous_health: dict[str, Any],
) -> dict[str, Any]:
    counts = Counter(str(sensor.get("health_status") or "offline") for sensor in sensors)
    rssi_values = [
        value
        for sensor in sensors
        if (value := _safe_float(sensor.get("rssi_dbm"))) is not None
    ]
    battery_rows = [
        sensor
        for sensor in sensors
        if _safe_float(sensor.get("battery_value")) is not None
    ]
    total = len(sensors)
    return {
        "online": counts["online"],
        "delayed": counts["delayed"],
        "offline": counts["offline"],
        "total": total,
        "reporting_pct": (counts["online"] / total * 100) if total else 0,
        "freshness_minutes": previous_health.get("freshness_minutes", 180),
        "average_rssi": sum(rssi_values) / len(rssi_values) if rssi_values else None,
        "minimum_rssi": min(rssi_values) if rssi_values else None,
        "maximum_rssi": max(rssi_values) if rssi_values else None,
        "rssi_coverage": len(rssi_values),
        "battery_coverage": len(battery_rows),
        "battery_sensors": sorted(
            battery_rows,
            key=lambda item: float(item.get("battery_value") or 0),
        )[:5],
    }


def _filtered_locations(sensors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"sensor_count": 0, "sensors": []}
    )
    for sensor in sensors:
        location = (
            str(sensor.get("location") or "").strip()
            or str(sensor.get("asset_name") or "").strip()
            or "Sin ubicación asignada"
        )
        grouped[location]["sensor_count"] += 1
        grouped[location]["sensors"].append(sensor)
    return sorted(
        (
            {
                "name": name,
                "sensor_count": data["sensor_count"],
                "sensors": data["sensors"],
            }
            for name, data in grouped.items()
        ),
        key=lambda item: (-item["sensor_count"], item["name"]),
    )


def _filtered_types(sensors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(str(sensor.get("type_name") or "Sensor") for sensor in sensors)
    total = len(sensors)
    return [
        {
            "name": name,
            "count": count,
            "pct": (count / total * 100) if total else 0,
        }
        for name, count in counts.most_common()
    ]


def apply_vladimir_sensor_visibility(
    client: Client,
    overview: dict[str, Any] | None,
    dashboard: dict[str, Any],
) -> dict[str, Any] | None:
    """Align Vladimir overview analytics with OSIRIS-local sensor visibility."""

    if overview is None:
        return None

    registry = ClientSensor.objects.filter(client=client)
    if not registry.exists():
        return overview

    visible_ids = set(
        registry.filter(is_active=True, dashboard_enabled=True).values_list(
            "external_sensor_id", flat=True
        )
    )
    sensors = [
        sensor
        for sensor in overview.get("sensors", [])
        if str(sensor.get("id")) in visible_ids
    ]
    alarms = [
        alarm
        for alarm in overview.get("alarms", [])
        if str(alarm.get("sensor_id") or "") in visible_ids
    ]
    selected_sensor_id = str(dashboard.get("selected_sensor_id") or "")
    selected_sensor = next(
        (sensor for sensor in sensors if str(sensor.get("id")) == selected_sensor_id),
        None,
    )
    selected_sensor_alarms = [
        alarm for alarm in alarms if str(alarm.get("sensor_id") or "") == selected_sensor_id
    ]
    health = _filtered_health(sensors, overview.get("health") or {})
    counts = dict(overview.get("counts") or {})
    counts["sensors"] = len(sensors)
    metric_name = str(
        (dashboard.get("selected_metric") or {}).get("name")
        or dashboard.get("selected_metric_id")
        or "la variable"
    )

    overview.update(
        {
            "sensors": sensors,
            "selected_sensor": selected_sensor,
            "health": health,
            "locations": _filtered_locations(sensors),
            "sensor_types": _filtered_types(sensors),
            "counts": counts,
            "alarms": alarms,
            "selected_sensor_alarms": selected_sensor_alarms,
            "active_alarm_count": len(alarms),
            "insights": _analysis_insights(
                health,
                selected_sensor,
                dashboard.get("statistics") or {},
                alarms,
                metric_name,
            ),
        }
    )
    return overview
