from __future__ import annotations

from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

from aplicaciones.core.access import can_access_module
from aplicaciones.core.decorators import module_access_required

from .osiris_sensor_context import build_osiris_sensor_context


@require_GET
@module_access_required("dashboard")
def sensor_context(request):
    """Return OSIRIS-owned context for the selected sensor and operational map."""

    selected_sensor_id = str(request.GET.get("sensor") or "").strip()
    payload = build_osiris_sensor_context(request.client, selected_sensor_id)

    selected = payload.get("selected")
    if selected is not None and can_access_module(request.user, "sensor_configuration"):
        selected["configure_url"] = reverse(
            "sensor_configuration_detail",
            args=(selected["sensor_pk"],),
        )
    else:
        if selected is not None:
            selected["configure_url"] = ""

    return JsonResponse(payload)
