from __future__ import annotations

import json
import unicodedata
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from aplicaciones.core.access import can_access_module
from aplicaciones.core.decorators import module_access_required
from aplicaciones.sensor_config.models import ClientSensor

from .adapters import get_adapter
from .models import AgronomicVariableRelationship


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(character for character in text if not unicodedata.combining(character)).lower()


def _metric_key(metric: dict[str, Any]) -> str:
    return f"{metric.get('id', '')}:{int(metric.get('probe_no') or 0)}"


def _serialise_metric(metric: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": _metric_key(metric),
        "id": str(metric.get("id") or ""),
        "name": str(metric.get("name") or metric.get("id") or "Variable"),
        "probe_no": int(metric.get("probe_no") or 0),
        "unit": str(metric.get("unit") or ""),
    }


def _metric_text(metric: dict[str, Any]) -> str:
    return _normalise(f"{metric.get('id', '')} {metric.get('name', '')}")


def _find_metric(
    metrics: list[dict[str, Any]],
    include: tuple[str, ...],
    exclude: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    for metric in metrics:
        text = _metric_text(metric)
        if any(term in text for term in exclude):
            continue
        if any(term in text for term in include):
            return metric
    return None


def _suggested_relationships(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    temperature = _find_metric(
        metrics,
        ("temperature", "temperatura"),
        ("soil", "suelo", "substrate", "sustrato"),
    )
    humidity = _find_metric(
        metrics,
        ("relative humidity", "humidity", "humedad relativa"),
        ("soil", "suelo", "moisture", "sustrato"),
    )
    soil_temperature = _find_metric(
        metrics,
        ("soil temperature", "temperatura suelo", "substrate temperature", "temperatura sustrato"),
    )
    soil_moisture = _find_metric(
        metrics,
        ("soil moisture", "humedad suelo", "substrate moisture", "vwc", "water content"),
    )
    ec = _find_metric(
        metrics,
        ("electrical conductivity", "conductivity", "conductividad", " ec", "ec "),
    )
    ph = _find_metric(metrics, (" ph", "ph ", "acidity", "acidez"))
    co2 = _find_metric(metrics, ("co2", "carbon dioxide", "dioxido de carbono"))
    light = _find_metric(
        metrics,
        ("par", "ppfd", "light", "lux", "radiation", "radiacion", "luz"),
    )
    leaf_wetness = _find_metric(
        metrics,
        ("leaf wetness", "mojado foliar", "wetness"),
    )

    suggestions: list[dict[str, Any]] = []

    def add(
        name: str,
        relation_type: str,
        selected: list[dict[str, Any] | None],
        goal: str,
        guidance: str,
    ) -> None:
        usable = [metric for metric in selected if metric is not None]
        unique = {str(metric["key"]): metric for metric in usable}
        if len(unique) < 2:
            return
        suggestions.append(
            {
                "name": name,
                "relationship_type": relation_type,
                "variable_keys": list(unique),
                "agronomic_goal": goal,
                "expert_guidance": guidance,
            }
        )

    add(
        "Balance climático y transpiración",
        AgronomicVariableRelationship.RelationshipType.CLIMATE,
        [temperature, humidity],
        "Interpretar simultáneamente temperatura y humedad para anticipar estrés climático y demanda de agua.",
        (
            "En Alstroemeria conviene evitar interpretar la temperatura de forma aislada. "
            "Su efecto debe leerse junto con la humedad relativa y, cuando sea posible, "
            "derivar VPD para evaluar la demanda evaporativa del cultivo."
        ),
    )
    add(
        "Zona radicular y fertirriego",
        AgronomicVariableRelationship.RelationshipType.ROOT_ZONE,
        [soil_temperature, soil_moisture, ec, ph],
        "Relacionar estado hídrico, temperatura radicular y concentración de sales/nutrientes.",
        (
            "Alstroemeria responde de forma marcada a la temperatura de la zona radicular. "
            "Humedad, EC y pH deben analizarse en conjunto para distinguir déficit de agua, "
            "acumulación de sales y problemas de disponibilidad de nutrientes."
        ),
    )
    add(
        "Ambiente fotosintético",
        AgronomicVariableRelationship.RelationshipType.PHOTOSYNTHESIS,
        [co2, light, temperature],
        "Evaluar si CO₂, radiación y temperatura están alineados para sostener crecimiento y floración.",
        (
            "La respuesta a CO₂ depende de que exista luz suficiente y una temperatura compatible "
            "con el cultivo. La relación permite evitar conclusiones basadas únicamente en CO₂."
        ),
    )
    add(
        "Riesgo sanitario por microclima",
        AgronomicVariableRelationship.RelationshipType.DISEASE_RISK,
        [temperature, humidity, leaf_wetness],
        "Detectar periodos de microclima favorable a enfermedades antes de observar síntomas.",
        (
            "Temperatura y humedad sostenida deben analizarse juntas; si existe mojado foliar, "
            "incorporarlo mejora la interpretación del riesgo sanitario."
        ),
    )
    return suggestions


def _relationship_payload(relationship: AgronomicVariableRelationship) -> dict[str, Any]:
    return {
        "id": relationship.pk,
        "crop_name": relationship.crop_name,
        "name": relationship.name,
        "relationship_type": relationship.relationship_type,
        "relationship_type_label": relationship.get_relationship_type_display(),
        "variable_ids": relationship.variable_ids,
        "variable_names": relationship.variable_names,
        "agronomic_goal": relationship.agronomic_goal,
        "expert_guidance": relationship.expert_guidance,
        "is_enabled": relationship.is_enabled,
        "updated_at": relationship.updated_at.isoformat(),
    }


def _sensor_for_request(request: HttpRequest, sensor_id: str) -> ClientSensor | None:
    return ClientSensor.objects.filter(
        client=request.client,
        external_sensor_id=sensor_id,
        is_active=True,
        dashboard_enabled=True,
    ).first()


def _available_metrics(request: HttpRequest, sensor_id: str) -> list[dict[str, Any]]:
    source = request.client.data_source
    adapter = get_adapter(source)
    return [_serialise_metric(metric) for metric in adapter.list_metrics(sensor_id)]


@require_http_methods(["GET", "POST"])
@module_access_required("dashboard")
def agronomy_relationships(request: HttpRequest) -> JsonResponse:
    sensor_id = str(
        request.GET.get("sensor") if request.method == "GET" else request.POST.get("sensor")
        or ""
    ).strip()
    sensor = _sensor_for_request(request, sensor_id)
    if sensor is None:
        return JsonResponse({"error": "Sensor no disponible en el dashboard."}, status=404)

    metrics = _available_metrics(request, sensor_id)
    allowed_metrics = {metric["key"]: metric for metric in metrics}

    if request.method == "POST":
        if not can_access_module(request.user, "sensor_configuration"):
            return JsonResponse({"error": "No tienes permiso para configurar relaciones."}, status=403)

        action = str(request.POST.get("action") or "save").strip()
        if action == "delete":
            relationship_id = request.POST.get("relationship_id")
            deleted, _ = AgronomicVariableRelationship.objects.filter(
                pk=relationship_id,
                client=request.client,
                sensor_id=sensor_id,
            ).delete()
            return JsonResponse({"deleted": bool(deleted)})

        try:
            requested_keys = json.loads(str(request.POST.get("variable_ids") or "[]"))
        except json.JSONDecodeError:
            return JsonResponse({"error": "La lista de variables no es válida."}, status=400)

        selected_keys = [str(key) for key in requested_keys if str(key) in allowed_metrics]
        selected_keys = list(dict.fromkeys(selected_keys))
        if len(selected_keys) < 2:
            return JsonResponse(
                {"error": "Selecciona al menos dos variables reales del sensor."},
                status=400,
            )

        relationship_type = str(request.POST.get("relationship_type") or "custom")
        valid_types = {
            value for value, _label in AgronomicVariableRelationship.RelationshipType.choices
        }
        if relationship_type not in valid_types:
            relationship_type = AgronomicVariableRelationship.RelationshipType.CUSTOM

        name = str(request.POST.get("name") or "").strip()[:200]
        crop_name = str(request.POST.get("crop_name") or "").strip()[:160]
        if not name or not crop_name:
            return JsonResponse({"error": "Cultivo y nombre de relación son obligatorios."}, status=400)

        selected_metrics = [allowed_metrics[key] for key in selected_keys]
        relationship, _created = AgronomicVariableRelationship.objects.update_or_create(
            client=request.client,
            sensor_id=sensor_id,
            name=name,
            defaults={
                "sensor_name": sensor.sensor_name or sensor.external_sensor_id,
                "crop_name": crop_name,
                "relationship_type": relationship_type,
                "variable_ids": selected_keys,
                "variable_names": [metric["name"] for metric in selected_metrics],
                "agronomic_goal": str(request.POST.get("agronomic_goal") or "").strip()[:500],
                "expert_guidance": str(request.POST.get("expert_guidance") or "").strip()[:2500],
                "is_enabled": request.POST.get("is_enabled", "1") == "1",
                "created_by": request.user,
            },
        )
        return JsonResponse({"relationship": _relationship_payload(relationship)})

    relationships = AgronomicVariableRelationship.objects.filter(
        client=request.client,
        sensor_id=sensor_id,
    )
    return JsonResponse(
        {
            "sensor_id": sensor_id,
            "sensor_name": sensor.sensor_name or sensor.external_sensor_id,
            "crop_name": sensor.product_name or "Astromelia",
            "can_edit": can_access_module(request.user, "sensor_configuration"),
            "metrics": metrics,
            "relationship_types": [
                {"value": value, "label": label}
                for value, label in AgronomicVariableRelationship.RelationshipType.choices
            ],
            "suggestions": _suggested_relationships(metrics),
            "relationships": [_relationship_payload(item) for item in relationships],
        }
    )
