from __future__ import annotations

import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from django.shortcuts import render

from aplicaciones.core.decorators import module_access_required

from .adapters.base import AdapterError
from .services import build_dashboard
from .vladimir_analytics import build_vladimir_analytics

logger = logging.getLogger(__name__)


@module_access_required("dashboard")
def dashboard(request):
    context = {"dashboard_error": None}
    template_name = "dashboard/dashboard.html"
    try:
        if request.client is None:
            raise AdapterError("Tu cuenta no tiene un cliente activo asignado.")
        context.update(build_dashboard(request.client, request.GET))
        if request.client.slug == "vladimir":
            template_name = "dashboard/vladimir.html"
            context["vladimir_analytics"] = build_vladimir_analytics(
                request.client,
                context,
                request.GET,
            )
    except ObjectDoesNotExist:
        context["dashboard_error"] = "El cliente todavía no tiene una fuente de datos configurada."
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
