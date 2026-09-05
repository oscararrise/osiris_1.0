from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render

from aplicaciones.core.decorators import module_access_required

from .forms import SensorLocationForm
from .models import ClientSensor, SensorPlacement, Zone
from .services import save_sensor_location_configuration


def _current_placement_initial(placement: SensorPlacement | None) -> dict[str, object]:
    if placement is None:
        return {"facility_type": Zone.ZoneType.GREENHOUSE}

    facility = placement.farm_or_greenhouse
    zone_name = ""
    if facility is not None and placement.zone_id != facility.id:
        zone_name = placement.zone.name

    return {
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

    total = base_queryset.filter(is_active=True).count()
    configured = base_queryset.filter(is_active=True, has_current_placement=True).count()
    inactive = base_queryset.filter(is_active=False).count()

    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all").strip()
    sensors = base_queryset
    if search:
        sensors = sensors.filter(
            Q(sensor_name__icontains=search)
            | Q(external_sensor_id__icontains=search)
            | Q(sensor_detail__icontains=search)
        )
    if status == "configured":
        sensors = sensors.filter(is_active=True, has_current_placement=True)
    elif status == "unconfigured":
        sensors = sensors.filter(is_active=True, has_current_placement=False)
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
                "total": total,
                "configured": configured,
                "unconfigured": max(total - configured, 0),
                "inactive": inactive,
            },
        },
    )


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
                _, changed = save_sensor_location_configuration(
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
            except ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
            else:
                if changed:
                    messages.success(request, "Ubicación del sensor guardada correctamente.")
                else:
                    messages.info(request, "La configuración ya estaba actualizada.")
                return redirect("sensor_configuration_detail", sensor_pk=sensor.pk)
    else:
        form = SensorLocationForm(initial=_current_placement_initial(current))

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
            "history": history,
        },
    )
