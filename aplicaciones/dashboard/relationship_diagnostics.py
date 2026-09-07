from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_http_methods

from aplicaciones.core.access import can_access_module
from aplicaciones.core.decorators import module_access_required
from aplicaciones.sensor_config.models import ClientSensor

from .adapters import get_adapter
from .adapters.base import AdapterError
from .models import AgronomicRelationshipAlert, AgronomicVariableRelationship


RELATIONSHIP_RANGES: dict[str, tuple[str, timedelta, int]] = {
    "24h": ("Últimas 24 horas", timedelta(hours=24), 300),
    "7d": ("Últimos 7 días", timedelta(days=7), 1800),
    "30d": ("Últimos 30 días", timedelta(days=30), 7200),
    "90d": ("Últimos 90 días", timedelta(days=90), 21600),
}


def _relationship_for_request(request: HttpRequest, relationship_id: int):
    return get_object_or_404(
        AgronomicVariableRelationship,
        pk=relationship_id,
        client=request.client,
    )


def _parse_variable_key(
    relationship: AgronomicVariableRelationship,
    stored_key: object,
) -> tuple[str, str, int] | None:
    key = str(stored_key)
    if "::" in key:
        sensor_id, local_key = key.split("::", 1)
    else:
        sensor_id, local_key = relationship.sensor_id, key
    if ":" not in local_key:
        return None
    metric_id, probe_text = local_key.rsplit(":", 1)
    try:
        probe_no = int(probe_text)
    except (TypeError, ValueError):
        return None
    if not sensor_id or not metric_id:
        return None
    return sensor_id, metric_id, probe_no


def _resolve_variables(
    relationship: AgronomicVariableRelationship,
) -> tuple[Any, list[dict[str, Any]]]:
    adapter = get_adapter(relationship.client.data_source)
    parsed = [_parse_variable_key(relationship, key) for key in relationship.variable_ids]
    sensor_ids = {item[0] for item in parsed if item is not None}
    configured_sensor_ids = set(
        ClientSensor.objects.filter(
            client=relationship.client,
            external_sensor_id__in=sensor_ids,
        ).values_list("external_sensor_id", flat=True)
    )

    metrics_by_sensor: dict[str, list[dict[str, Any]]] = {}
    sensors = {
        sensor.external_sensor_id: sensor
        for sensor in ClientSensor.objects.filter(
            client=relationship.client,
            external_sensor_id__in=sensor_ids,
        )
    }
    variables: list[dict[str, Any]] = []

    for index, stored_key in enumerate(relationship.variable_ids):
        key = str(stored_key)
        stored_name = (
            str(relationship.variable_names[index])
            if index < len(relationship.variable_names)
            else key
        )
        parsed_key = _parse_variable_key(relationship, stored_key)
        if parsed_key is None:
            variables.append(
                {
                    "key": key,
                    "name": stored_name,
                    "sensor_id": relationship.sensor_id,
                    "sensor_name": relationship.sensor_name or relationship.sensor_id,
                    "metric_id": "",
                    "probe_no": 0,
                    "unit": "",
                    "available": False,
                    "error": "Identificador de variable no válido.",
                }
            )
            continue

        sensor_id, metric_id, probe_no = parsed_key
        if sensor_id not in configured_sensor_ids:
            variables.append(
                {
                    "key": key,
                    "name": stored_name,
                    "sensor_id": sensor_id,
                    "sensor_name": sensor_id,
                    "metric_id": metric_id,
                    "probe_no": probe_no,
                    "unit": "",
                    "available": False,
                    "error": "El sensor ya no está registrado para este cliente.",
                }
            )
            continue

        if sensor_id not in metrics_by_sensor:
            try:
                metrics_by_sensor[sensor_id] = adapter.list_metrics(sensor_id)
            except AdapterError:
                metrics_by_sensor[sensor_id] = []

        metric = next(
            (
                item
                for item in metrics_by_sensor[sensor_id]
                if str(item.get("id") or "") == metric_id
                and int(item.get("probe_no") or 0) == probe_no
            ),
            None,
        )
        sensor = sensors.get(sensor_id)
        variables.append(
            {
                "key": key,
                "name": str(metric.get("name") or stored_name) if metric else stored_name,
                "sensor_id": sensor_id,
                "sensor_name": (
                    sensor.sensor_name if sensor and sensor.sensor_name else sensor_id
                ),
                "metric_id": metric_id,
                "probe_no": probe_no,
                "unit": str(metric.get("unit") or "") if metric else "",
                "available": metric is not None,
                "error": "" if metric else "La métrica ya no está disponible en la fuente.",
            }
        )
    return adapter, variables


def _point_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    else:
        result = parse_datetime(str(value or ""))
    if result is None:
        return None
    if timezone.is_naive(result):
        result = timezone.make_aware(result, timezone.get_current_timezone())
    return result.astimezone(UTC)


def _load_variable_series(
    adapter,
    variable: dict[str, Any],
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    if not variable["available"]:
        return []
    return adapter.time_series(
        variable["sensor_id"],
        variable["metric_id"],
        variable["probe_no"],
        start,
        end,
        max(int(getattr(settings, "DASHBOARD_MAX_POINTS", 600)), 400),
    )


def _align_series(
    variables: list[dict[str, Any]],
    series_by_key: dict[str, list[dict[str, Any]]],
    bucket_seconds: int,
) -> list[dict[str, Any]]:
    buckets: dict[int, dict[str, dict[str, float]]] = {}
    for variable in variables:
        key = variable["key"]
        for point in series_by_key.get(key, []):
            measured_at = _point_datetime(point.get("measured_at"))
            if measured_at is None or point.get("value") is None:
                continue
            try:
                value = float(point["value"])
                weight = max(int(point.get("sample_count") or 1), 1)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue

            epoch = int(measured_at.timestamp())
            bucket = epoch - (epoch % bucket_seconds)
            slot = buckets.setdefault(bucket, {}).setdefault(
                key,
                {"weighted": 0.0, "weight": 0.0, "latest_epoch": 0.0},
            )
            slot["weighted"] += value * weight
            slot["weight"] += weight
            slot["latest_epoch"] = max(slot["latest_epoch"], float(epoch))

    rows: list[dict[str, Any]] = []
    for bucket in sorted(buckets):
        values: dict[str, float | None] = {}
        source_times: dict[str, str | None] = {}
        for variable in variables:
            key = variable["key"]
            slot = buckets[bucket].get(key)
            values[key] = (
                slot["weighted"] / slot["weight"]
                if slot and slot["weight"]
                else None
            )
            source_times[key] = (
                datetime.fromtimestamp(slot["latest_epoch"], tz=UTC).isoformat()
                if slot and slot["latest_epoch"]
                else None
            )
        measured_at = datetime.fromtimestamp(bucket, tz=UTC)
        rows.append(
            {
                "measured_at": measured_at.isoformat(),
                "values": values,
                "source_times": source_times,
            }
        )
    return rows


def _series_statistics(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [
        float(row["values"][key])
        for row in rows
        if row["values"].get(key) is not None
    ]
    if not values:
        return {
            "current": None,
            "minimum": None,
            "maximum": None,
            "average": None,
            "points": 0,
        }
    return {
        "current": values[-1],
        "minimum": min(values),
        "maximum": max(values),
        "average": sum(values) / len(values),
        "points": len(values),
    }


def _metric_text(variable: dict[str, Any]) -> str:
    return f"{variable.get('metric_id', '')} {variable.get('name', '')}".casefold()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _find_temperature_humidity_pair(
    variables: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    temperature = None
    humidity = None
    for variable in variables:
        if not variable.get("available"):
            continue
        text = _metric_text(variable)
        if temperature is None and _contains_any(
            text,
            ("air_temperature", "air temperature", "temperature", "temperatura"),
        ):
            if not _contains_any(text, ("soil", "suelo", "substrate", "sustrato")):
                temperature = variable
        if humidity is None and _contains_any(
            text,
            ("relative_humidity", "relative humidity", "humedad relativa", "humidity"),
        ):
            if not _contains_any(
                text,
                ("soil", "suelo", "moisture", "sustrato", "substrate"),
            ):
                humidity = variable
    if temperature is None or humidity is None:
        return None
    return temperature, humidity


def _vpd_kpa(temperature_c: float, relative_humidity: float) -> float | None:
    if not (-50.0 <= temperature_c <= 70.0):
        return None
    if not (0.0 <= relative_humidity <= 100.0):
        return None
    saturation = 0.6108 * math.exp(
        (17.27 * temperature_c) / (temperature_c + 237.3)
    )
    return saturation * (1.0 - relative_humidity / 100.0)


def _add_vpd(
    rows: list[dict[str, Any]],
    variables: list[dict[str, Any]],
) -> dict[str, Any] | None:
    pair = _find_temperature_humidity_pair(variables)
    if pair is None:
        return None
    temperature, humidity = pair
    for row in rows:
        temperature_value = row["values"].get(temperature["key"])
        humidity_value = row["values"].get(humidity["key"])
        row["values"]["__vpd__"] = (
            _vpd_kpa(float(temperature_value), float(humidity_value))
            if temperature_value is not None and humidity_value is not None
            else None
        )
    return {
        "key": "__vpd__",
        "name": "VPD",
        "sensor_id": "osiris",
        "sensor_name": "OSIRIS · variable derivada",
        "metric_id": "vpd",
        "probe_no": 0,
        "unit": "kPa",
        "available": True,
        "derived": True,
        "temperature_key": temperature["key"],
        "humidity_key": humidity["key"],
    }


def _pearson_correlation(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 3:
        return None
    xs = [pair[0] for pair in pairs]
    ys = [pair[1] for pair in pairs]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    sum_x = sum((x - mean_x) ** 2 for x in xs)
    sum_y = sum((y - mean_y) ** 2 for y in ys)
    denominator = math.sqrt(sum_x * sum_y)
    if denominator == 0:
        return None
    return numerator / denominator


def _correlation_label(value: float | None) -> str:
    if value is None:
        return "Sin suficientes datos sincronizados"
    magnitude = abs(value)
    if magnitude >= 0.7:
        strength = "fuerte"
    elif magnitude >= 0.4:
        strength = "moderada"
    elif magnitude >= 0.2:
        strength = "débil"
    else:
        strength = "muy débil"
    direction = "directa" if value >= 0 else "inversa"
    return f"Asociación descriptiva {strength} y {direction}"


def _analysis_summary(
    variables: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    derived_vpd: dict[str, Any] | None,
) -> dict[str, Any]:
    available = [variable for variable in variables if variable.get("available")]
    pair = available[:2]
    pair_payload = None
    aligned_pairs: list[tuple[float, float]] = []

    if len(pair) == 2:
        variable_a, variable_b = pair
        for row in rows:
            value_a = row["values"].get(variable_a["key"])
            value_b = row["values"].get(variable_b["key"])
            if value_a is None or value_b is None:
                continue
            aligned_pairs.append((float(value_a), float(value_b)))
        pair_payload = {
            "variable_a_key": variable_a["key"],
            "variable_a_name": variable_a["name"],
            "variable_a_unit": variable_a.get("unit", ""),
            "variable_a_sensor": variable_a.get("sensor_name", ""),
            "variable_b_key": variable_b["key"],
            "variable_b_name": variable_b["name"],
            "variable_b_unit": variable_b.get("unit", ""),
            "variable_b_sensor": variable_b.get("sensor_name", ""),
        }

    correlation = _pearson_correlation(aligned_pairs)
    capabilities = [
        {
            "key": "timeseries",
            "label": "Comparación temporal",
            "available": bool(rows and available),
            "reason": "Series disponibles en el periodo seleccionado.",
        },
        {
            "key": "scatter",
            "label": "Dispersión entre variables",
            "available": len(aligned_pairs) >= 2,
            "reason": (
                f"{len(aligned_pairs)} intervalos contienen ambas variables."
                if aligned_pairs
                else "No hay intervalos con ambas variables disponibles."
            ),
        },
        {
            "key": "correlation",
            "label": "Correlación descriptiva",
            "available": correlation is not None,
            "reason": _correlation_label(correlation),
        },
        {
            "key": "vpd",
            "label": "VPD",
            "available": derived_vpd is not None,
            "reason": (
                "Temperatura ambiente y humedad relativa detectadas."
                if derived_vpd is not None
                else "Requiere temperatura ambiente y humedad relativa reales."
            ),
        },
    ]
    return {
        "pair": pair_payload,
        "aligned_points": len(aligned_pairs),
        "correlation": correlation,
        "correlation_label": _correlation_label(correlation),
        "capabilities": capabilities,
        "available_variable_count": len(available),
        "configured_variable_count": len(variables),
    }


def _compare(value: float | None, operator: str, threshold: float) -> bool:
    if value is None:
        return False
    if operator == "gt":
        return value > threshold
    if operator == "gte":
        return value >= threshold
    if operator == "lt":
        return value < threshold
    if operator == "lte":
        return value <= threshold
    return False


def _row_pair_state(
    row: dict[str, Any],
    alert: AgronomicRelationshipAlert,
) -> tuple[float | None, float | None, datetime | None, datetime | None]:
    value_a = row.get("values", {}).get(alert.variable_a_key)
    value_b = row.get("values", {}).get(alert.variable_b_key)
    source_times = row.get("source_times", {})
    source_a = _point_datetime(source_times.get(alert.variable_a_key))
    source_b = _point_datetime(source_times.get(alert.variable_b_key))
    return value_a, value_b, source_a, source_b


def _alert_evaluation(
    alert: AgronomicRelationshipAlert,
    rows: list[dict[str, Any]],
    bucket_seconds: int,
    *,
    now: datetime | None = None,
    freshness_minutes: int | None = None,
) -> dict[str, Any]:
    now = (now or timezone.now()).astimezone(UTC)
    freshness_minutes = freshness_minutes or int(
        getattr(settings, "AGRONOMY_ALERT_MAX_STALENESS_MINUTES", 15)
    )

    latest_index = None
    latest_state = None
    for index in range(len(rows) - 1, -1, -1):
        state = _row_pair_state(rows[index], alert)
        value_a, value_b, source_a, source_b = state
        if value_a is None or value_b is None or source_a is None or source_b is None:
            continue
        latest_index = index
        latest_state = state
        break

    if latest_index is None or latest_state is None:
        return {
            "conditions_met_now": False,
            "condition_a_met": False,
            "condition_b_met": False,
            "data_fresh": False,
            "synchronized": False,
            "stale_reason": "No hay un intervalo reciente con ambas variables.",
            "sustained_minutes": 0.0,
            "triggered_preview": False,
            "value_a": None,
            "value_b": None,
            "age_a_minutes": None,
            "age_b_minutes": None,
            "freshness_limit_minutes": freshness_minutes,
        }

    value_a, value_b, source_a, source_b = latest_state
    age_a = max((now - source_a).total_seconds() / 60.0, 0.0)
    age_b = max((now - source_b).total_seconds() / 60.0, 0.0)
    sample_gap_seconds = abs((source_a - source_b).total_seconds())
    synchronized = sample_gap_seconds <= bucket_seconds
    data_fresh = (
        age_a <= freshness_minutes
        and age_b <= freshness_minutes
        and synchronized
    )

    condition_a = _compare(float(value_a), alert.operator_a, alert.threshold_a)
    condition_b = _compare(float(value_b), alert.operator_b, alert.threshold_b)
    conditions_met = (
        condition_a and condition_b
        if alert.logic == AgronomicRelationshipAlert.Logic.AND
        else condition_a or condition_b
    )

    stale_reason = ""
    if not synchronized:
        stale_reason = "Las dos lecturas no pertenecen a una ventana temporal compatible."
    elif age_a > freshness_minutes or age_b > freshness_minutes:
        stale_reason = (
            "La vista previa se bloqueó porque al menos una lectura está desactualizada."
        )

    sustained_minutes = 0.0
    if data_fresh and conditions_met:
        latest_bucket = _point_datetime(rows[latest_index].get("measured_at"))
        oldest_bucket = latest_bucket
        previous_bucket = latest_bucket
        for index in range(latest_index, -1, -1):
            row = rows[index]
            bucket_time = _point_datetime(row.get("measured_at"))
            value_a_row, value_b_row, source_a_row, source_b_row = _row_pair_state(
                row, alert
            )
            if (
                bucket_time is None
                or value_a_row is None
                or value_b_row is None
                or source_a_row is None
                or source_b_row is None
            ):
                break
            if previous_bucket is not None:
                gap = abs((previous_bucket - bucket_time).total_seconds())
                if gap > bucket_seconds * 1.5:
                    break
            if abs((source_a_row - source_b_row).total_seconds()) > bucket_seconds:
                break
            match_a = _compare(
                float(value_a_row), alert.operator_a, alert.threshold_a
            )
            match_b = _compare(
                float(value_b_row), alert.operator_b, alert.threshold_b
            )
            matches = (
                match_a and match_b
                if alert.logic == AgronomicRelationshipAlert.Logic.AND
                else match_a or match_b
            )
            if not matches:
                break
            oldest_bucket = bucket_time
            previous_bucket = bucket_time

        if latest_bucket is not None and oldest_bucket is not None:
            sustained_minutes = (
                (latest_bucket - oldest_bucket).total_seconds() + bucket_seconds
            ) / 60.0

    return {
        "conditions_met_now": conditions_met and data_fresh,
        "condition_a_met": condition_a,
        "condition_b_met": condition_b,
        "data_fresh": data_fresh,
        "synchronized": synchronized,
        "stale_reason": stale_reason,
        "sustained_minutes": sustained_minutes,
        "triggered_preview": (
            data_fresh
            and conditions_met
            and sustained_minutes >= alert.duration_minutes
        ),
        "value_a": float(value_a),
        "value_b": float(value_b),
        "age_a_minutes": age_a,
        "age_b_minutes": age_b,
        "sample_gap_minutes": sample_gap_seconds / 60.0,
        "freshness_limit_minutes": freshness_minutes,
    }


def _alert_payload(
    alert: AgronomicRelationshipAlert,
    variable_lookup: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
    bucket_seconds: int,
) -> dict[str, Any]:
    variable_a = variable_lookup.get(alert.variable_a_key, {})
    variable_b = variable_lookup.get(alert.variable_b_key, {})
    return {
        "id": alert.pk,
        "name": alert.name,
        "variable_a_key": alert.variable_a_key,
        "variable_a_name": variable_a.get("name", alert.variable_a_key),
        "variable_a_sensor": variable_a.get("sensor_name", ""),
        "variable_a_unit": variable_a.get("unit", ""),
        "operator_a": alert.operator_a,
        "operator_a_label": alert.get_operator_a_display(),
        "threshold_a": alert.threshold_a,
        "variable_b_key": alert.variable_b_key,
        "variable_b_name": variable_b.get("name", alert.variable_b_key),
        "variable_b_sensor": variable_b.get("sensor_name", ""),
        "variable_b_unit": variable_b.get("unit", ""),
        "operator_b": alert.operator_b,
        "operator_b_label": alert.get_operator_b_display(),
        "threshold_b": alert.threshold_b,
        "logic": alert.logic,
        "logic_label": alert.get_logic_display(),
        "duration_minutes": alert.duration_minutes,
        "cooldown_minutes": alert.cooldown_minutes,
        "severity": alert.severity,
        "severity_label": alert.get_severity_display(),
        "email_enabled": alert.email_enabled,
        "email_recipients": alert.email_recipients,
        "whatsapp_enabled": alert.whatsapp_enabled,
        "whatsapp_recipients": alert.whatsapp_recipients,
        "is_enabled": alert.is_enabled,
        "evaluation": _alert_evaluation(alert, rows, bucket_seconds),
    }


def _relationship_payload(
    relationship: AgronomicVariableRelationship,
    range_key: str,
) -> dict[str, Any]:
    if range_key not in RELATIONSHIP_RANGES:
        range_key = "24h"
    _label, delta, bucket_seconds = RELATIONSHIP_RANGES[range_key]
    end = timezone.now().astimezone(UTC)
    start = end - delta

    adapter, variables = _resolve_variables(relationship)
    series_by_key: dict[str, list[dict[str, Any]]] = {}
    for variable in variables:
        try:
            series_by_key[variable["key"]] = _load_variable_series(
                adapter, variable, start, end
            )
        except AdapterError as exc:
            variable["available"] = False
            variable["error"] = str(exc)
            series_by_key[variable["key"]] = []

    rows = _align_series(variables, series_by_key, bucket_seconds)
    derived_vpd = _add_vpd(rows, variables)
    display_variables = [*variables]
    if derived_vpd is not None:
        display_variables.append(derived_vpd)

    statistics = {
        variable["key"]: _series_statistics(rows, variable["key"])
        for variable in display_variables
    }
    analysis = _analysis_summary(variables, rows, derived_vpd)
    variable_lookup = {variable["key"]: variable for variable in variables}
    alerts = [
        _alert_payload(alert, variable_lookup, rows, bucket_seconds)
        for alert in relationship.alerts.all()
    ]

    return {
        "relationship": {
            "id": relationship.pk,
            "name": relationship.name,
            "crop_name": relationship.crop_name,
            "relationship_type": relationship.relationship_type,
            "relationship_type_label": relationship.get_relationship_type_display(),
            "agronomic_goal": relationship.agronomic_goal,
            "expert_guidance": relationship.expert_guidance,
            "is_enabled": relationship.is_enabled,
        },
        "variables": display_variables,
        "alert_variables": variables,
        "rows": rows,
        "latest_rows": list(reversed(rows[-25:])),
        "statistics": statistics,
        "analysis": analysis,
        "vpd_available": derived_vpd is not None,
        "alerts": alerts,
        "ranges": [
            {"key": key, "label": value[0]}
            for key, value in RELATIONSHIP_RANGES.items()
        ],
        "selected_range": range_key,
        "bucket_minutes": bucket_seconds // 60,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
    }


@module_access_required("dashboard")
def agronomy_relationship_detail(request: HttpRequest, relationship_id: int):
    relationship = _relationship_for_request(request, relationship_id)
    return render(
        request,
        "dashboard/agronomy_relationship_detail.html",
        {
            "relationship": relationship,
            "can_edit_relationship": can_access_module(
                request.user, "sensor_configuration"
            ),
        },
    )


@require_GET
@module_access_required("dashboard")
def agronomy_relationship_detail_data(
    request: HttpRequest, relationship_id: int
) -> JsonResponse:
    relationship = _relationship_for_request(request, relationship_id)
    try:
        payload = _relationship_payload(
            relationship, str(request.GET.get("range") or "24h")
        )
    except AdapterError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    payload["can_edit"] = can_access_module(request.user, "sensor_configuration")
    return JsonResponse(payload)


@require_http_methods(["POST"])
@module_access_required("dashboard")
def agronomy_relationship_alerts(
    request: HttpRequest, relationship_id: int
) -> JsonResponse:
    relationship = _relationship_for_request(request, relationship_id)
    if not can_access_module(request.user, "sensor_configuration"):
        return JsonResponse(
            {"error": "No tienes permiso para configurar alertas."}, status=403
        )

    if request.POST.get("action") == "delete":
        alert_id = request.POST.get("alert_id")
        deleted, _ = AgronomicRelationshipAlert.objects.filter(
            pk=alert_id,
            client=request.client,
            relationship=relationship,
        ).delete()
        return JsonResponse({"deleted": bool(deleted)})

    name = str(request.POST.get("name") or "").strip()[:200]
    variable_a_key = str(request.POST.get("variable_a_key") or "").strip()
    variable_b_key = str(request.POST.get("variable_b_key") or "").strip()
    allowed_keys = {str(key) for key in relationship.variable_ids}
    if not name:
        return JsonResponse(
            {"error": "El nombre de la alerta es obligatorio."}, status=400
        )
    if variable_a_key not in allowed_keys or variable_b_key not in allowed_keys:
        return JsonResponse(
            {"error": "Selecciona variables reales de esta relación."}, status=400
        )
    if variable_a_key == variable_b_key:
        return JsonResponse(
            {"error": "La alerta debe comparar dos variables diferentes."}, status=400
        )

    valid_operators = {
        value for value, _ in AgronomicRelationshipAlert.Operator.choices
    }
    operator_a = str(request.POST.get("operator_a") or "gt")
    operator_b = str(request.POST.get("operator_b") or "gt")
    if operator_a not in valid_operators or operator_b not in valid_operators:
        return JsonResponse(
            {"error": "Operador de comparación no válido."}, status=400
        )

    try:
        threshold_a = float(request.POST.get("threshold_a", ""))
        threshold_b = float(request.POST.get("threshold_b", ""))
        duration_minutes = int(request.POST.get("duration_minutes", "10"))
        cooldown_minutes = int(request.POST.get("cooldown_minutes", "30"))
    except (TypeError, ValueError):
        return JsonResponse(
            {"error": "Umbrales, duración y cooldown deben ser numéricos."},
            status=400,
        )
    if not math.isfinite(threshold_a) or not math.isfinite(threshold_b):
        return JsonResponse(
            {"error": "Los umbrales deben ser valores finitos."}, status=400
        )
    if not 1 <= duration_minutes <= 1440:
        return JsonResponse(
            {"error": "La duración debe estar entre 1 y 1440 minutos."}, status=400
        )
    if not 1 <= cooldown_minutes <= 10080:
        return JsonResponse(
            {"error": "El cooldown debe estar entre 1 minuto y 7 días."}, status=400
        )

    logic = str(request.POST.get("logic") or "and")
    valid_logic = {value for value, _ in AgronomicRelationshipAlert.Logic.choices}
    if logic not in valid_logic:
        logic = AgronomicRelationshipAlert.Logic.AND
    severity = str(request.POST.get("severity") or "medium")
    valid_severity = {
        value for value, _ in AgronomicRelationshipAlert.Severity.choices
    }
    if severity not in valid_severity:
        severity = AgronomicRelationshipAlert.Severity.MEDIUM

    alert, created = AgronomicRelationshipAlert.objects.update_or_create(
        relationship=relationship,
        name=name,
        defaults={
            "client": request.client,
            "variable_a_key": variable_a_key,
            "operator_a": operator_a,
            "threshold_a": threshold_a,
            "variable_b_key": variable_b_key,
            "operator_b": operator_b,
            "threshold_b": threshold_b,
            "logic": logic,
            "duration_minutes": duration_minutes,
            "cooldown_minutes": cooldown_minutes,
            "severity": severity,
            "email_enabled": request.POST.get("email_enabled") == "1",
            "email_recipients": str(
                request.POST.get("email_recipients") or ""
            ).strip()[:500],
            "whatsapp_enabled": request.POST.get("whatsapp_enabled") == "1",
            "whatsapp_recipients": str(
                request.POST.get("whatsapp_recipients") or ""
            ).strip()[:500],
            "is_enabled": request.POST.get("is_enabled", "1") == "1",
            "created_by": request.user,
        },
    )
    return JsonResponse({"saved": True, "created": created, "alert_id": alert.pk})
