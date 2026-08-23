from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from datetime import datetime
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import connections
from django.utils import timezone

from aplicaciones.core.models import Client, ClientDataSource

from .adapters import get_adapter


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _percent_delta(current: float | None, reference: float | None) -> float | None:
    if current is None or reference in (None, 0):
        return None
    return ((current - reference) / abs(reference)) * 100


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * min(max(fraction, 0), 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _cache_key(client: Client, section: str, *parts: object) -> str:
    identity = "|".join(str(part) for part in (client.pk, section, *parts))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"osiris:vladimir:{digest}"


def _normalise_dt(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _series_values(series: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for point in series:
        value = _safe_float(point.get("value"))
        if value is not None:
            values.append(value)
    return values


def _linear_trend(series: list[dict[str, Any]]) -> dict[str, float | None]:
    points: list[tuple[float, float]] = []
    first_time: datetime | None = None
    for point in series:
        timestamp = _normalise_dt(point.get("measured_at"))
        value = _safe_float(point.get("value"))
        if timestamp is None or value is None:
            continue
        if first_time is None:
            first_time = timestamp
        elapsed_hours = (timestamp - first_time).total_seconds() / 3600
        points.append((elapsed_hours, value))

    if len(points) < 2:
        return {"slope_per_hour": None, "slope_per_day": None}

    mean_x = sum(x for x, _ in points) / len(points)
    mean_y = sum(y for _, y in points) / len(points)
    denominator = sum((x - mean_x) ** 2 for x, _ in points)
    if denominator == 0:
        return {"slope_per_hour": None, "slope_per_day": None}
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator
    return {"slope_per_hour": slope, "slope_per_day": slope * 24}


def _histogram(values: list[float], bins: int = 10) -> list[dict[str, float | int]]:
    if not values:
        return []
    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        return [{"start": minimum, "end": maximum, "count": len(values)}]

    width = (maximum - minimum) / max(bins, 1)
    counts = [0] * bins
    for value in values:
        index = min(int((value - minimum) / width), bins - 1)
        counts[index] += 1
    return [
        {
            "start": minimum + index * width,
            "end": minimum + (index + 1) * width,
            "count": count,
        }
        for index, count in enumerate(counts)
    ]


def _hourly_profile(series: list[dict[str, Any]]) -> list[dict[str, float | int | None]]:
    buckets: dict[int, dict[str, float]] = defaultdict(lambda: {"total": 0.0, "weight": 0.0})
    for point in series:
        timestamp = _normalise_dt(point.get("measured_at"))
        value = _safe_float(point.get("value"))
        if timestamp is None or value is None:
            continue
        local_timestamp = timezone.localtime(timestamp)
        weight = max(int(point.get("sample_count") or 1), 1)
        buckets[local_timestamp.hour]["total"] += value * weight
        buckets[local_timestamp.hour]["weight"] += weight

    profile: list[dict[str, float | int | None]] = []
    for hour in range(24):
        bucket = buckets.get(hour)
        average = None
        samples = 0
        if bucket and bucket["weight"]:
            average = bucket["total"] / bucket["weight"]
            samples = int(bucket["weight"])
        profile.append({"hour": hour, "average": average, "samples": samples})
    return profile


def _distribution_profile(series: list[dict[str, Any]]) -> dict[str, Any]:
    values = _series_values(series)
    q10 = _percentile(values, 0.10)
    q25 = _percentile(values, 0.25)
    median = _percentile(values, 0.50)
    q75 = _percentile(values, 0.75)
    q90 = _percentile(values, 0.90)
    iqr = (q75 - q25) if q25 is not None and q75 is not None else None
    lower_fence = q25 - 1.5 * iqr if q25 is not None and iqr is not None else None
    upper_fence = q75 + 1.5 * iqr if q75 is not None and iqr is not None else None

    outliers: list[dict[str, Any]] = []
    if lower_fence is not None and upper_fence is not None:
        for point in series:
            value = _safe_float(point.get("value"))
            if value is not None and (value < lower_fence or value > upper_fence):
                outliers.append(
                    {
                        "measured_at": point.get("measured_at"),
                        "value": value,
                        "direction": "high" if value > upper_fence else "low",
                    }
                )

    return {
        "q10": q10,
        "q25": q25,
        "median": median,
        "q75": q75,
        "q90": q90,
        "iqr": iqr,
        "lower_fence": lower_fence,
        "upper_fence": upper_fence,
        "outliers": outliers[-12:],
        "outlier_count": len(outliers),
        "histogram": _histogram(values),
        "trend": _linear_trend(series),
    }


def _correlation(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
) -> dict[str, Any]:
    primary_by_time: dict[str, float] = {}
    for point in primary:
        timestamp = _normalise_dt(point.get("measured_at"))
        value = _safe_float(point.get("value"))
        if timestamp is not None and value is not None:
            primary_by_time[timestamp.isoformat()] = value

    pairs: list[dict[str, Any]] = []
    for point in secondary:
        timestamp = _normalise_dt(point.get("measured_at"))
        secondary_value = _safe_float(point.get("value"))
        if timestamp is None or secondary_value is None:
            continue
        key = timestamp.isoformat()
        primary_value = primary_by_time.get(key)
        if primary_value is None:
            continue
        pairs.append(
            {
                "measured_at": timestamp,
                "primary": primary_value,
                "secondary": secondary_value,
            }
        )

    if len(pairs) < 3:
        return {"coefficient": None, "strength": "Sin datos suficientes", "pairs": pairs}

    xs = [pair["primary"] for pair in pairs]
    ys = [pair["secondary"] for pair in pairs]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    denominator_x = sum((x - mean_x) ** 2 for x in xs)
    denominator_y = sum((y - mean_y) ** 2 for y in ys)
    denominator = math.sqrt(denominator_x * denominator_y)
    coefficient = numerator / denominator if denominator else None

    if coefficient is None:
        strength = "Sin variación suficiente"
    else:
        magnitude = abs(coefficient)
        if magnitude >= 0.80:
            level = "Muy fuerte"
        elif magnitude >= 0.60:
            level = "Fuerte"
        elif magnitude >= 0.40:
            level = "Moderada"
        elif magnitude >= 0.20:
            level = "Débil"
        else:
            level = "Muy débil"
        direction = "positiva" if coefficient > 0 else "negativa" if coefficient < 0 else "neutra"
        strength = f"{level} · {direction}"

    return {"coefficient": coefficient, "strength": strength, "pairs": pairs}


def _choose_comparison_metric(
    metrics: list[dict[str, Any]],
    selected_metric_id: str,
    selected_probe_no: int,
    requested_metric_id: str,
    requested_probe: str,
) -> dict[str, Any] | None:
    try:
        requested_probe_no = int(requested_probe)
    except (TypeError, ValueError):
        requested_probe_no = 0

    requested = next(
        (
            metric
            for metric in metrics
            if str(metric.get("id")) == requested_metric_id
            and int(metric.get("probe_no") or 0) == requested_probe_no
            and not (
                str(metric.get("id")) == selected_metric_id
                and int(metric.get("probe_no") or 0) == selected_probe_no
            )
        ),
        None,
    )
    if requested is not None:
        return requested

    primary_name = ""
    for metric in metrics:
        if str(metric.get("id")) == selected_metric_id and int(metric.get("probe_no") or 0) == selected_probe_no:
            primary_name = str(metric.get("name") or metric.get("id") or "").lower()
            break

    preferred_words: tuple[str, ...]
    if "moist" in primary_name or "humedad" in primary_name:
        preferred_words = ("temperature", "temperatura", "ec", "conduct")
    elif "temp" in primary_name:
        preferred_words = ("humidity", "humedad", "moist", "co2")
    elif "co2" in primary_name:
        preferred_words = ("temperature", "humidity", "temperatura", "humedad")
    else:
        preferred_words = ("temperature", "humidity", "moist", "ec", "co2")

    alternatives = [
        metric
        for metric in metrics
        if not (
            str(metric.get("id")) == selected_metric_id
            and int(metric.get("probe_no") or 0) == selected_probe_no
        )
    ]
    for word in preferred_words:
        for metric in alternatives:
            name = str(metric.get("name") or metric.get("id") or "").lower()
            if word in name:
                return metric
    return alternatives[0] if alternatives else None


def _fleet_metric_snapshot(
    database_alias: str,
    metric_id: str,
    probe_no: int,
) -> list[dict[str, Any]]:
    sql = """
        SELECT DISTINCT ON (latest.source_sensor_id)
            latest.source_sensor_id AS sensor_id,
            COALESCE(NULLIF(sensor.name, ''), NULLIF(sensor.sensor_code, ''), sensor.id) AS sensor_name,
            sensor.sensor_code AS sensor_code,
            latest.value,
            latest.measured_at,
            COALESCE(unit.name, latest.unit_id, '') AS unit,
            status.rssi_dbm,
            status.battery_value,
            COALESCE(battery_unit.name, status.battery_unit_id, '') AS battery_unit
        FROM aranet.v_latest_measurements AS latest
        JOIN aranet.sensor AS sensor
          ON sensor.id = latest.source_sensor_id AND sensor.is_active
        LEFT JOIN aranet.unit AS unit ON unit.id = latest.unit_id
        LEFT JOIN aranet.v_sensor_status AS status ON status.sensor_id = sensor.id
        LEFT JOIN aranet.unit AS battery_unit ON battery_unit.id = status.battery_unit_id
        WHERE latest.metric_id = %s
          AND latest.probe_no = %s
        ORDER BY latest.source_sensor_id, latest.measured_at DESC
    """
    with connections[database_alias].cursor() as cursor:
        cursor.execute(sql, (metric_id, probe_no))
        columns = [column[0] for column in cursor.description]
        rows = []
        for row in cursor.fetchall():
            rows.append(dict(zip(columns, row, strict=True)))
        return rows


def _fleet_summary(
    rows: list[dict[str, Any]],
    selected_sensor_id: str,
) -> dict[str, Any]:
    valid_rows = []
    values: list[float] = []
    now = timezone.now()
    for row in rows:
        value = _safe_float(row.get("value"))
        if value is None:
            continue
        measured_at = _normalise_dt(row.get("measured_at"))
        age_minutes = None
        if measured_at is not None:
            age_minutes = max((now - measured_at).total_seconds() / 60, 0)
        item = {**row, "value": value, "age_minutes": age_minutes}
        valid_rows.append(item)
        values.append(value)

    valid_rows.sort(key=lambda row: row["value"], reverse=True)
    for index, row in enumerate(valid_rows, start=1):
        row["rank"] = index

    selected = next(
        (row for row in valid_rows if str(row.get("sensor_id")) == selected_sensor_id),
        None,
    )
    median = _percentile(values, 0.50)
    selected_delta = _percent_delta(selected.get("value") if selected else None, median)
    percentile_rank = None
    if selected and values:
        percentile_rank = 100 * sum(value <= selected["value"] for value in values) / len(values)

    return {
        "rows": valid_rows,
        "count": len(valid_rows),
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "median": median,
        "q25": _percentile(values, 0.25),
        "q75": _percentile(values, 0.75),
        "selected": selected,
        "selected_delta_vs_median_pct": selected_delta,
        "selected_percentile_rank": percentile_rank,
    }


def _agronomic_focus(metric_name: str) -> dict[str, str]:
    name = metric_name.lower()
    if "moist" in name or "humedad" in name:
        return {
            "title": "Dinámica hídrica",
            "text": "Cruza el descenso sostenido de humedad con temperatura y variabilidad. La señal es útil para revisar ventanas de riego, pero el umbral óptimo debe definirse por suelo, profundidad y cultivo.",
        }
    if "temp" in name:
        return {
            "title": "Carga térmica y amplitud diaria",
            "text": "Más que un valor aislado, revisa la amplitud entre percentiles, el perfil horario y su relación con humedad u otra variable ambiental.",
        }
    if "conduct" in name or name.strip() == "ec" or "salin" in name:
        return {
            "title": "Concentración y estabilidad",
            "text": "Busca cambios persistentes y dispersión entre sensores. EC y salinidad deben interpretarse junto con humedad, temperatura y estrategia de fertirriego.",
        }
    if "co2" in name:
        return {
            "title": "Ventilación y dinámica ambiental",
            "text": "La correlación con temperatura y humedad ayuda a separar patrones operativos de cambios ambientales. Correlación no implica causalidad.",
        }
    if "humidity" in name or "humedad" in name:
        return {
            "title": "Balance ambiental",
            "text": "Revisa el perfil horario y su relación con temperatura. Los cambios simultáneos suelen ser más informativos que una lectura puntual.",
        }
    return {
        "title": "Lectura contextual",
        "text": "Combina tendencia, dispersión, posición frente a la flota y relación con una segunda variable antes de concluir que existe un cambio operativo real.",
    }


def build_vladimir_analytics(
    client: Client,
    dashboard: dict[str, Any],
    query: Any,
) -> dict[str, Any] | None:
    source = dashboard.get("source")
    selected_metric = dashboard.get("selected_metric")
    selected_sensor = dashboard.get("selected_sensor")
    if (
        source is None
        or selected_metric is None
        or selected_sensor is None
        or source.adapter_key != ClientDataSource.Adapter.ARANET
    ):
        return None

    selected_metric_id = str(dashboard.get("selected_metric_id") or selected_metric.get("id") or "")
    selected_probe_no = int(dashboard.get("selected_probe_no") or 0)
    selected_sensor_id = str(dashboard.get("selected_sensor_id") or selected_sensor.get("id") or "")
    series = dashboard.get("series") or []
    metrics = dashboard.get("metrics") or []

    comparison_metric = _choose_comparison_metric(
        metrics,
        selected_metric_id,
        selected_probe_no,
        str(query.get("compare_metric", "")),
        str(query.get("compare_probe", "0")),
    )

    comparison_series: list[dict[str, Any]] = []
    if comparison_metric is not None:
        adapter = get_adapter(source)
        compare_metric_id = str(comparison_metric.get("id"))
        compare_probe_no = int(comparison_metric.get("probe_no") or 0)
        period_start = dashboard.get("period_start")
        period_end = dashboard.get("period_end")
        if period_start is not None and period_end is not None:
            series_key = _cache_key(
                client,
                "compare-series",
                selected_sensor_id,
                compare_metric_id,
                compare_probe_no,
                dashboard.get("selected_range"),
                period_end.replace(second=0, microsecond=0).isoformat(),
            )
            comparison_series = cache.get(series_key)
            if comparison_series is None:
                comparison_series = adapter.time_series(
                    selected_sensor_id,
                    compare_metric_id,
                    compare_probe_no,
                    period_start,
                    period_end,
                    settings.DASHBOARD_MAX_POINTS,
                )
                cache.set(series_key, comparison_series, settings.DASHBOARD_CACHE_TTL)

    snapshot_key = _cache_key(
        client,
        "fleet-snapshot",
        selected_metric_id,
        selected_probe_no,
        timezone.now().replace(minute=0, second=0, microsecond=0).isoformat(),
    )
    fleet_rows = cache.get(snapshot_key)
    if fleet_rows is None:
        fleet_rows = _fleet_metric_snapshot(source.database_alias, selected_metric_id, selected_probe_no)
        cache.set(snapshot_key, fleet_rows, max(settings.DASHBOARD_CACHE_TTL, 300))

    distribution = _distribution_profile(series)
    correlation = _correlation(series, comparison_series) if comparison_series else {
        "coefficient": None,
        "strength": "Selecciona una segunda variable",
        "pairs": [],
    }
    fleet_metric = _fleet_summary(fleet_rows, selected_sensor_id)
    metric_name = str(selected_metric.get("name") or selected_metric_id)

    advanced_insights: list[dict[str, str]] = []
    if distribution["outlier_count"]:
        advanced_insights.append(
            {
                "tone": "attention",
                "title": "Puntos atípicos detectados",
                "text": f"Se identificaron {distribution['outlier_count']} buckets fuera de las cercas IQR. Revisa si coinciden con eventos reales, mantenimiento o huecos de transmisión.",
            }
        )
    coefficient = correlation.get("coefficient")
    if coefficient is not None and abs(coefficient) >= 0.60 and comparison_metric is not None:
        advanced_insights.append(
            {
                "tone": "neutral",
                "title": "Relación estadística relevante",
                "text": f"{metric_name} y {comparison_metric.get('name')} muestran una correlación {correlation['strength'].lower()} (r={coefficient:.2f}). Úsala como señal exploratoria, no como prueba causal.",
            }
        )
    selected_delta = fleet_metric.get("selected_delta_vs_median_pct")
    if selected_delta is not None and abs(selected_delta) >= 15:
        direction = "por encima" if selected_delta > 0 else "por debajo"
        advanced_insights.append(
            {
                "tone": "attention",
                "title": "Sensor separado de la mediana de flota",
                "text": f"La última lectura está {abs(selected_delta):.1f}% {direction} de la mediana entre sensores que reportan esta métrica. Conviene comprobar contexto y ubicación antes de tratarlo como anomalía.",
            }
        )

    return {
        "comparison_metric": comparison_metric,
        "comparison_series": comparison_series,
        "correlation": correlation,
        "distribution": distribution,
        "hourly_profile": _hourly_profile(series),
        "fleet_metric": fleet_metric,
        "agronomic_focus": _agronomic_focus(metric_name),
        "advanced_insights": advanced_insights,
    }
