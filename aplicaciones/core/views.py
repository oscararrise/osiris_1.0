from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .access import accessible_modules, membership_for
from .decorators import module_access_required
from .models import ClientDataSource


def root(request):
    return redirect("inicio" if request.user.is_authenticated else "login")


def _data_source_for(membership):
    if membership is None:
        return None
    return getattr(membership.client, "data_source", None)


@login_required
def operations(request):
    membership = membership_for(request.user)
    data_source = _data_source_for(membership)

    # Los clientes de telemetría conservan la experiencia histórica de OSIRIS
    # (grid.html y sus módulos). Aranet mantiene el centro de operaciones nuevo.
    if (
        data_source is not None
        and data_source.is_active
        and data_source.adapter_key == ClientDataSource.Adapter.TELEMETRY
    ):
        from aplicaciones.automatizacion import views as legacy_views
        from aplicaciones.satellite.legacy import augment_legacy_home_response

        response = legacy_views.inicio(request)
        return augment_legacy_home_response(request, response)

    return render(
        request,
        "core/operations.html",
        {"membership": membership, "modules": accessible_modules(request.user)},
    )


@module_access_required("dashboard")
def sensor_dashboard(request):
    """Dispatch the sensor dashboard according to the authenticated client's source."""

    membership = membership_for(request.user)
    data_source = _data_source_for(membership)

    if (
        data_source is not None
        and data_source.is_active
        and data_source.adapter_key == ClientDataSource.Adapter.TELEMETRY
    ):
        from aplicaciones.automatizacion import views as legacy_views

        return legacy_views.s2(request)

    from aplicaciones.dashboard import views as dashboard_views

    return dashboard_views.dashboard(request)
