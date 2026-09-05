from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from aplicaciones.core.decorators import module_access_required

from .forms import SensorLocationForm
from .models import ClientSensor, SensorPlacement, Zone
from .services import save_sensor_location_configuration


def _sensor_configuration_initial(
    sensor: ClientSensor,
    placement: SensorPlacement | None,
) -> dict[str, object]:
    initial: dict[str, object] = {
        "activity_type": sensor.activity_type,
        "product_name": sensor.product_name,
        "facility_type": Zone.ZoneType.GREENHOUSE,
    }
    if placement is None:
        return initial

    facility = placement.farm_or_greenhouse
    zone_name = ""
    if facility is not None and placement.zone_id != facility.id:
        zone_name = placement.zone.name

    initial.update(
        {
            "facility_type": (
                facility.zone_type if facility is not None else Zone.ZoneType.GREENHOUSE
            ),
            "facility_name": facility.name if facility is not None else "",
            "zone_name": zone_name,
            "city": placement.city,
            "department": placement.department,
            "latitude": placement.latitude,
            "longitude": placement.longitude,
            "altitude_m": placement.altitude_m,
            "notes": placement.notes,
        }
    )
    return initial


def _return_after_sensor_action(request, fallback_name: str, **kwargs):
    next_url = str(request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(fallback_name, **kwargs)


@module_access_required("sensor_configuration")
def sensor_configuration(request):
    client = request.client
    current_placement_exists = SensorPlacement.objects.filter(
        sensor_id=OuterRef("pk"),
        valid_until__isnull=True,
    )
    base_queryset = ClientSensor.objects.filter(client=client).annotate(
        has_current_placement=Exists(current_placement_exists)
    )

    source_active = base_queryset.filter(is_active=True).count()
    dashboard_visible = base_queryset.filter(
        is_active=True,
        dashboard_enabled=True,
    ).count()
    dashboard_hidden = base_queryset.filter(
        is_active=True,
        dashboard_enabled=False,
    ).count()
    configured = base_queryset.filter(is_active=True, has_current_placement=True).count()
    productive_context = base_queryset.filter(is_active=True).exclude(activity_type="").count()
    inactive = base_queryset.filter(is_active=False).count()

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all").strip()
    sensors = base_queryset
    if search:
        sensors = sensors.filter(
            Q(sensor_name__icontains=search)
            | Q(external_sensor_id__icontains=search)
            | Q(sensor_detail__icontains=search)
            | Q(product_name__icontains=search)
            | Q(activity_type__icontains=search)
        )
    if status == "visible":
        sensors = sensors.filter(is_active=True, dashboard_enabled=True)
    elif status == "hidden":
        sensors = sensors.filter(is_active=True, dashboard_enabled=False)
    elif status == "configured":
        sensors = sensors.filter(is_active=True, has_current_placement=True)
    elif status == "unconfigured":
        sensors = sensors.filter(is_active=True, has_current_placement=False)
    elif status == "productive":
        sensors = sensors.filter(is_active=True).exclude(activity_type="")
    elif status == "inactive":
        sensors = sensors.filter(is_active=False)
    else:
        sensors = sensors.filter(is_active=True)

    current_placements = SensorPlacement.objects.filter(
        valid_until__isnull=True
    ).select_related("zone", "zone__parent")
    sensors = sensors.prefetch_related(
        Prefetch("placements", queryset=current_placements, to_attr="active_placements")
    )

    return render(
        request,
        "sensor_config/sensor_list.html",
        {
            "sensors": sensors,
            "search": search,
            "status": status,
            "stats": {
                "source_active": source_active,
                "dashboard_visible": dashboard_visible,
                "dashboard_hidden": dashboard_hidden,
                "configured": configured,
                "productive_context": productive_context,
                "unconfigured": max(source_active - configured, 0),
                "inactive": inactive,
            },
        },
    )


@require_POST
@module_access_required("sensor_configuration")
def toggle_sensor_dashboard(request, sensor_pk: int):
    sensor = get_object_or_404(ClientSensor, pk=sensor_pk, client=request.client)
    enable = request.POST.get("enabled") == "1"

    if enable and not sensor.is_active:
        messages.warning(
            request,
            "Este sensor está inactivo en la fuente externa y no puede mostrarse en el dashboard.",
        )
    elif sensor.dashboard_enabled != enable:
        sensor.dashboard_enabled = enable
        sensor.save(update_fields=("dashboard_enabled", "updated_at"))
        if enable:
            messages.success(
                request,
                f"{sensor.sensor_name or sensor.external_sensor_id} ahora aparece en el dashboard.",
            )
        else:
            messages.success(
                request,
                f"{sensor.sensor_name or sensor.external_sensor_id} se ocultó del dashboard.",
            )
    else:
        messages.info(request, "El sensor ya tenía ese estado en el dashboard.")

    return _return_after_sensor_action(request, "sensor_configuration")


@module_access_required("sensor_configuration")
def sensor_configuration_detail(request, sensor_pk: int):
    client = request.client
    sensor = get_object_or_404(ClientSensor, pk=sensor_pk, client=client)
    current = (
        SensorPlacement.objects.filter(sensor=sensor, valid_until__isnull=True)
        .select_related("zone", "zone__parent")
        .first()
    )

    if request.method == "POST":
        form = SensorLocationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    _, location_changed = save_sensor_location_configuration(
                        sensor=sensor,
                        facility_name=form.cleaned_data["facility_name"],
                        facility_type=form.cleaned_data["facility_type"],
                        zone_name=form.cleaned_data["zone_name"],
                        city=form.cleaned_data["city"],
                        department=form.cleaned_data["department"],
                        latitude=form.cleaned_data["latitude"],
                        longitude=form.cleaned_data["longitude"],
                        altitude_m=form.cleaned_data["altitude_m"],
                        notes=form.cleaned_data["notes"],
                        changed_by=request.user,
                    )

                    desired_context = {
                        "activity_type": form.cleaned_data["activity_type"],
                        "product_name": form.cleaned_data["product_name"].strip()[:160],
                    }
                    context_changed_fields = []
                    for field, value in desired_context.items():
                        if getattr(sensor, field) != value:
                            setattr(sensor, field, value)
                            context_changed_fields.append(field)
                    if context_changed_fields:
                        sensor.save(update_fields=(*context_changed_fields, "updated_at"))
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
            else:
                if location_changed or context_changed_fields:
                    messages.success(
                        request,
                        "Configuración operativa del sensor guardada correctamente.",
                    )
                else:
                    messages.info(request, "La configuración ya estaba actualizada.")
                return redirect("sensor_configuration_detail", sensor_pk=sensor.pk)
    else:
        form = SensorLocationForm(initial=_sensor_configuration_initial(sensor, current))

    facilities = Zone.objects.filter(
        client=client,
        parent__isnull=True,
        zone_type__in=(Zone.ZoneType.FARM, Zone.ZoneType.GREENHOUSE),
        is_active=True,
    ).order_by("name")
    zone_names = (
        Zone.objects.filter(client=client, parent__isnull=False, is_active=True)
        .order_by("name")
        .values_list("name", flat=True)
        .distinct()
    )
    product_names = (
        ClientSensor.objects.filter(client=client)
        .exclude(product_name="")
        .order_by("product_name")
        .values_list("product_name", flat=True)
        .distinct()
    )
    history = (
        SensorPlacement.objects.filter(sensor=sensor)
        .select_related("zone", "zone__parent", "created_by")
        .order_by("-valid_from")[:8]
    )

    return render(
        request,
        "sensor_config/sensor_detail.html",
        {
            "sensor": sensor,
            "current": current,
            "form": form,
            "facilities": facilities,
            "zone_names": zone_names,
            "product_names": product_names,
            "history": history,
        },
    )
