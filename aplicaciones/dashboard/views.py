from __future__ import annotations

import logging
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from django.shortcuts import redirect, render

from aplicaciones.core.decorators import module_access_required

from .adapters.base import AdapterError
from .models import SensorAutomationPolicy
from .services import build_dashboard
from .vladimir_overview import build_vladimir_overview

logger = logging.getLogger(__name__)


def _optional_float(value: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _save_automation_policy(request, context: dict) -> SensorAutomationPolicy:
    selected_sensor = context.get("selected_sensor") or {}
    selected_sensor_id = str(context.get("selected_sensor_id") or "")
    if not selected_sensor_id:
        raise AdapterError("No hay un sensor válido seleccionado para configurar.")

    metrics = context.get("metrics") or []
    metric_id = str(request.POST.get("automation_metric", "")).strip()
    metric = next(
        (item for item in metrics if str(item.get("id")) == metric_id),
        None,
    )

    automation_level = str(request.POST.get("automation_level", "recommend"))
    valid_levels = {value for value, _label in SensorAutomationPolicy.AutomationLevel.choices}
    if automation_level not in valid_levels:
        automation_level = SensorAutomationPolicy.AutomationLevel.RECOMMEND

    operator = str(request.POST.get("operator", "gt"))
    valid_operators = {value for value, _label in SensorAutomationPolicy.Operator.choices}
    if operator not in valid_operators:
        operator = SensorAutomationPolicy.Operator.GREATER_THAN

    try:
        cooldown_minutes = int(request.POST.get("cooldown_minutes", "30"))
    except ValueError:
        cooldown_minutes = 30
    cooldown_minutes = min(max(cooldown_minutes, 1), 10080)

    defaults = {
        "sensor_name": str(selected_sensor.get("name") or selected_sensor_id)[:200],
        "is_enabled": request.POST.get("is_enabled") == "on",
        "metric_id": metric_id[:120] if metric else "",
        "metric_name": str(metric.get("name") or metric_id)[:160] if metric else "",
        "operator": operator,
        "threshold_value": _optional_float(str(request.POST.get("threshold_value", ""))),
        "cooldown_minutes": cooldown_minutes,
        "email_enabled": request.POST.get("email_enabled") == "on",
        "email_recipients": str(request.POST.get("email_recipients", ""))[:500].strip(),
        "whatsapp_enabled": request.POST.get("whatsapp_enabled") == "on",
        "whatsapp_recipients": str(request.POST.get("whatsapp_recipients", ""))[:500].strip(),
        "automation_level": automation_level,
        "requires_confirmation": request.POST.get("requires_confirmation") == "on",
        "ai_instruction": str(request.POST.get("ai_instruction", ""))[:2500].strip(),
        "updated_by": request.user,
    }
    policy, _created = SensorAutomationPolicy.objects.update_or_create(
        client=request.client,
        sensor_id=selected_sensor_id,
        defaults=defaults,
    )
    return policy


@module_access_required("dashboard")
def dashboard(request):
    context = {"dashboard_error": None}
    template_name = "dashboard/dashboard.html"
    try:
        if request.client is None:
            raise AdapterError("Tu cuenta no tiene un cliente activo asignado.")

        query = request.POST if request.method == "POST" else request.GET
        context.update(build_dashboard(request.client, query))

        if request.client.slug == "vladimir":
            template_name = "dashboard/vladimir.html"
            context["vladimir_overview"] = build_vladimir_overview(request.client, context)

            if request.method == "POST" and request.POST.get("action") == "save_automation":
                _save_automation_policy(request, context)
                messages.success(
                    request,
                    "Configuración demo de AI Automation guardada para este sensor.",
                )
                params = urlencode(
                    {
                        "sensor": context.get("selected_sensor_id", ""),
                        "metric": context.get("selected_metric_id", ""),
                        "probe": context.get("selected_probe_no", 0),
                        "range": context.get("selected_range", "24h"),
                        "configure": "1",
                        "saved": "1",
                    }
                )
                return redirect(f"/dashboard/?{params}")

            selected_sensor_id = str(context.get("selected_sensor_id") or "")
            context["automation_policy"] = SensorAutomationPolicy.objects.filter(
                client=request.client,
                sensor_id=selected_sensor_id,
            ).first()
            context["automation_levels"] = SensorAutomationPolicy.AutomationLevel.choices
            context["automation_operators"] = SensorAutomationPolicy.Operator.choices
            context["open_automation_modal"] = request.GET.get("configure") == "1"

    except ObjectDoesNotExist:
        context["dashboard_error"] = (
            "El cliente todavía no tiene una fuente de datos configurada."
        )
    except AdapterError as exc:
        context["dashboard_error"] = str(exc)
    except DatabaseError:
        logger.exception(
            "Client sensor database is unavailable",
            extra={"client_id": getattr(request.client, "pk", None)},
        )
        context["dashboard_error"] = (
            "No pudimos consultar los sensores en este momento. Intenta nuevamente en unos minutos."
        )
    return render(request, template_name, context)
