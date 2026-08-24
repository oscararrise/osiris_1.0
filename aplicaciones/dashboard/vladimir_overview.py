from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import connections
from django.utils import timezone

from aplicaciones.core.models import Client, ClientDataSource

from .adapters import get_adapter


def _cache_key(client: Client, section: str, *parts: object) -> str:
    identity = "|".join(str(part) for part in (client.pk, section, *parts))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"osiris:vladimir-overview:{digest}"


def _query(
    database_alias: str,
    sql: str,
    params: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    with connections[database_alias].cursor() as cursor:
        cursor.execute(sql, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _normalise_dt(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _sensor_inventory(database_alias: str) -> list[dict[str, Any]]:
    return _query(
        database_alias,
        """
        SELECT
            sensor.id,
            COALESCE(
                NULLIF(sensor.name, ''),
                NULLIF(sensor.sensor_code, ''),
                sensor.id
            ) AS name,
            sensor.sensor_code AS code,
            COALESCE(sensor_type.name, sensor.sensor_type_id, 'Sensor') AS type_name,
            status.last_telemetry_at AS last_seen_at,
            status.rssi_dbm,
            status.battery_value,
            COALESCE(battery_unit.name, status.battery_unit_id, '') AS battery_unit,
            pairing.base_station_id,
            pairing.base_station_name,
            pairing.base_region,
            placement.asset_id,
            placement.asset_name,
            placement.location,
            placement.measurement_point_id,
            placement.measurement_point_name,
            COALESCE(capability_data.metric_count, 0) AS metric_count
        FROM aranet.sensor AS sensor
        LEFT JOIN aranet.sensor_type AS sensor_type
          ON sensor_type.id = sensor.sensor_type_id
        LEFT JOIN aranet.v_sensor_status AS status
          ON status.sensor_id = sensor.id
        LEFT JOIN aranet.unit AS battery_unit
          ON battery_unit.id = status.battery_unit_id
        LEFT JOIN LATERAL (
            SELECT
                pair.base_station_id,
                COALESCE(NULLIF(base.name, ''), base.id) AS base_station_name,
                base.region AS base_region
            FROM aranet.sensor_base_pairing AS pair
            JOIN aranet.base_station AS base
              ON base.id = pair.base_station_id
            WHERE pair.sensor_id = sensor.id
              AND pair.removed_at IS NULL
              AND base.is_active
            ORDER BY pair.paired_at DESC NULLS LAST, pair.synced_at DESC
            LIMIT 1
        ) AS pairing ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                association.asset_id,
                COALESCE(NULLIF(asset.name, ''), asset.id) AS asset_name,
                asset.location,
                association.measurement_point_id,
                COALESCE(NULLIF(point.name, ''), point.id) AS measurement_point_name
            FROM aranet.asset_sensor_association AS association
            JOIN aranet.asset AS asset
              ON asset.id = association.asset_id
             AND asset.is_active
            JOIN aranet.measurement_point AS point
              ON point.id = association.measurement_point_id
             AND point.is_active
            WHERE association.sensor_id = sensor.id
              AND association.removed_at IS NULL
            ORDER BY association.placed_at DESC NULLS LAST, association.synced_at DESC
            LIMIT 1
        ) AS placement ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::integer AS metric_count
            FROM aranet.sensor_capability AS capability
            WHERE capability.sensor_id = sensor.id
              AND capability.is_active
        ) AS capability_data ON TRUE
        WHERE sensor.is_active
        ORDER BY name, sensor.id
        """,
    )


def _base_stations(database_alias: str) -> list[dict[str, Any]]:
    return _query(
        database_alias,
        """
        SELECT
            base.id,
            COALESCE(NULLIF(base.name, ''), base.id) AS name,
            base.product,
            base.firmware,
            base.region,
            base.last_seen_at_source AS last_seen_at,
            COUNT(DISTINCT pair.sensor_id)
                FILTER (WHERE pair.removed_at IS NULL) AS sensor_count
        FROM aranet.base_station AS base
        LEFT JOIN aranet.sensor_base_pairing AS pair
          ON pair.base_station_id = base.id
        WHERE base.is_active
        GROUP BY base.id
        ORDER BY name
        """,
    )


def _metric_coverage(database_alias: str) -> list[dict[str, Any]]:
    return _query(
        database_alias,
        """
        SELECT
            metric.id,
            COALESCE(NULLIF(metric.name, ''), metric.id) AS name,
            metric.kind,
            COUNT(DISTINCT capability.sensor_id) AS sensor_count
        FROM aranet.metric AS metric
        JOIN aranet.sensor_capability AS capability
          ON capability.metric_id = metric.id
         AND capability.is_active
        JOIN aranet.sensor AS sensor
          ON sensor.id = capability.sensor_id
         AND sensor.is_active
        WHERE metric.is_active
        GROUP BY metric.id
        ORDER BY sensor_count DESC, name
        """,
    )


def _catalog_counts(database_alias: str) -> dict[str, int]:
    rows = _query(
        database_alias,
        """
        SELECT
            (SELECT COUNT(*) FROM aranet.sensor WHERE is_active) AS sensors,
            (SELECT COUNT(*) FROM aranet.base_station WHERE is_active) AS bases,
            (SELECT COUNT(*) FROM aranet.asset WHERE is_active) AS assets,
            (
                SELECT COUNT(*)
                FROM aranet.measurement_point
                WHERE is_active
            ) AS measurement_points,
            (SELECT COUNT(*) FROM aranet.metric WHERE is_active) AS metrics
        """,
    )
    return rows[0] if rows else {}


def _enrich_health(
    sensors: list[dict[str, Any]],
    freshness_minutes: int,
) -> dict[str, Any]:
    now = timezone.now()
    counts = Counter()
    rssi_values: list[float] = []
    battery_rows: list[dict[str, Any]] = []

    for sensor in sensors:
        last_seen = _normalise_dt(sensor.get("last_seen_at"))
        age_minutes = None
        if last_seen is not None:
            age_minutes = max((now - last_seen).total_seconds() / 60, 0)

        if age_minutes is not None and age_minutes <= freshness_minutes:
            health_status = "online"
            health_label = "Reportando"
        elif age_minutes is not None and age_minutes <= freshness_minutes * 4:
            health_status = "delayed"
            health_label = "Con retraso"
        else:
            health_status = "offline"
            health_label = "Sin telemetría reciente"

        sensor["age_minutes"] = age_minutes
        sensor["health_status"] = health_status
        sensor["health_label"] = health_label
        counts[health_status] += 1

        rssi = _safe_float(sensor.get("rssi_dbm"))
        if rssi is not None:
            rssi_values.append(rssi)

        battery = _safe_float(sensor.get("battery_value"))
        if battery is not None:
            battery_rows.append(sensor)

    total = len(sensors)
    return {
        "online": counts["online"],
        "delayed": counts["delayed"],
        "offline": counts["offline"],
        "total": total,
        "reporting_pct": (counts["online"] / total * 100) if total else 0,
        "freshness_minutes": freshness_minutes,
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


def _location_groups(sensors: list[dict[str, Any]]) -> list[dict[str, Any]]:
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

    result = [
        {
            "name": name,
            "sensor_count": data["sensor_count"],
            "sensors": data["sensors"],
        }
        for name, data in grouped.items()
    ]
    return sorted(result, key=lambda item: (-item["sensor_count"], item["name"]))


def _type_groups(sensors: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def _analysis_insights(
    health: dict[str, Any],
    selected_sensor: dict[str, Any] | None,
    statistics: dict[str, Any],
    alarms: list[dict[str, Any]],
    metric_name: str,
) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []
    reporting_pct = float(health.get("reporting_pct") or 0)

    if reporting_pct >= 90:
        insights.append(
            {
                "tone": "good",
                "title": "Cobertura de telemetría alta",
                "text": (
                    f"{health['online']} de {health['total']} sensores están reportando "
                    "dentro de la ventana reciente."
                ),
            }
        )
    else:
        missing = int(health.get("delayed") or 0) + int(health.get("offline") or 0)
        insights.append(
            {
                "tone": "warn",
                "title": "Sensores que requieren revisión",
                "text": (
                    f"{missing} sensores presentan retraso o ausencia de telemetría reciente."
                ),
            }
        )

    if selected_sensor is not None:
        status = selected_sensor.get("health_status")
        if status != "online":
            insights.append(
                {
                    "tone": "warn",
                    "title": "Sensor seleccionado sin reporte reciente",
                    "text": (
                        f"{selected_sensor.get('name', 'El sensor')} aparece como "
                        f"{selected_sensor.get('health_label', 'sin telemetría reciente').lower()}."
                    ),
                }
            )
        else:
            rssi = _safe_float(selected_sensor.get("rssi_dbm"))
            if rssi is not None and rssi <= -90:
                insights.append(
                    {
                        "tone": "warn",
                        "title": "Señal inalámbrica baja",
                        "text": (
                            f"El RSSI actual del sensor es {rssi:.0f} dBm. "
                            "Conviene revisar cobertura y posición de la base station."
                        ),
                    }
                )

            battery = _safe_float(selected_sensor.get("battery_value"))
            battery_unit = str(selected_sensor.get("battery_unit") or "")
            if battery is not None and "%" in battery_unit and battery <= 20:
                insights.append(
                    {
                        "tone": "warn",
                        "title": "Batería baja",
                        "text": (
                            f"El sensor seleccionado reporta {battery:.0f}% de batería."
                        ),
                    }
                )

    average = _safe_float(statistics.get("average"))
    minimum = _safe_float(statistics.get("minimum"))
    maximum = _safe_float(statistics.get("maximum"))
    if average is not None and minimum is not None and maximum is not None:
        span = maximum - minimum
        relative_span = abs(span / average) * 100 if average else None
        text = f"En la ventana seleccionada, {metric_name} osciló {span:.2f} unidades."
        if relative_span is not None:
            text += f" El rango equivale al {relative_span:.1f}% del promedio."
        insights.append(
            {
                "tone": "info",
                "title": "Comportamiento de la variable",
                "text": text,
            }
        )

    if alarms:
        insights.append(
            {
                "tone": "risk",
                "title": "Alertas activas en Aranet",
                "text": f"Hay {len(alarms)} alerta(s) activa(s) en la flota.",
            }
        )
    else:
        insights.append(
            {
                "tone": "good",
                "title": "Sin alertas activas",
                "text": "Aranet no reporta reglas de alarma activas en este momento.",
            }
        )

    return insights[:4]


def build_vladimir_overview(
    client: Client,
    dashboard: dict[str, Any],
) -> dict[str, Any] | None:
    source = dashboard.get("source")
    if source is None or source.adapter_key != ClientDataSource.Adapter.ARANET:
        return None

    inventory_key = _cache_key(client, "inventory")
    sensors = cache.get(inventory_key)
    if sensors is None:
        sensors = _sensor_inventory(source.database_alias)
        cache.set(
            inventory_key,
            sensors,
            max(settings.DASHBOARD_CACHE_TTL, 300),
        )

    freshness_minutes = max(int(source.settings.get("freshness_minutes", 180)), 1)
    health = _enrich_health(sensors, freshness_minutes)

    catalog_key = _cache_key(client, "catalog")
    catalog = cache.get(catalog_key)
    if catalog is None:
        catalog = {
            "bases": _base_stations(source.database_alias),
            "metrics": _metric_coverage(source.database_alias),
            "counts": _catalog_counts(source.database_alias),
        }
        cache.set(
            catalog_key,
            catalog,
            max(settings.DASHBOARD_CACHE_TTL, 300),
        )

    adapter = get_adapter(source)
    alarm_key = _cache_key(client, "fleet-alarms")
    alarms = cache.get(alarm_key)
    if alarms is None:
        alarms = adapter.active_alarms(None)
        cache.set(
            alarm_key,
            alarms,
            min(settings.DASHBOARD_CACHE_TTL, 60),
        )

    selected_sensor_id = str(dashboard.get("selected_sensor_id") or "")
    selected_sensor = next(
        (sensor for sensor in sensors if str(sensor.get("id")) == selected_sensor_id),
        None,
    )
    locations = _location_groups(sensors)
    metric_name = str(
        (dashboard.get("selected_metric") or {}).get("name")
        or dashboard.get("selected_metric_id")
        or "la variable"
    )

    return {
        "sensors": sensors,
        "selected_sensor": selected_sensor,
        "health": health,
        "locations": locations,
        "sensor_types": _type_groups(sensors),
        "base_stations": catalog["bases"],
        "metric_coverage": catalog["metrics"],
        "counts": catalog["counts"],
        "alarms": alarms,
        "active_alarm_count": len(alarms),
        "insights": _analysis_insights(
            health,
            selected_sensor,
            dashboard.get("statistics") or {},
            alarms,
            metric_name,
        ),
    }
