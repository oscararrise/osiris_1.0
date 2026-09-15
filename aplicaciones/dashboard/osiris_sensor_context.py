from __future__ import annotations

from typing import Any

from django.db.models import Prefetch

from aplicaciones.core.models import Client
from aplicaciones.sensor_config.models import ClientSensor, SensorPlacement


def build_osiris_sensor_context(
    client: Client,
    selected_sensor_id: str,
) -> dict[str, Any]:
    """Build OSIRIS-owned productive and geographic context for the dashboard.

    Aranet remains the telemetry source of truth. This helper only reads metadata
    owned by OSIRIS: productive context, physical placement and coordinates.
    """

    current_placements = SensorPlacement.objects.filter(
        valid_until__isnull=True,
    ).select_related(
        "zone",
        "zone__parent",
        "zone__parent__parent",
        "zone__parent__parent__parent",
    )
    sensors = list(
        ClientSensor.objects.filter(
            client=client,
            is_active=True,
            dashboard_enabled=True,
        ).prefetch_related(
            Prefetch(
                "placements",
                queryset=current_placements,
                to_attr="dashboard_current_placements",
            )
        )
    )

    selected: dict[str, Any] | None = None
    map_points: list[dict[str, Any]] = []

    for sensor in sensors:
        placement = (
            sensor.dashboard_current_placements[0]
            if sensor.dashboard_current_placements
            else None
        )
        facility = placement.farm_or_greenhouse if placement is not None else None
        zone = placement.zone if placement is not None else None
        activity_label = sensor.get_activity_type_display() if sensor.activity_type else ""
        location_label = ""
        if zone is not None:
            location_label = zone.full_name
        elif placement is not None:
            location_label = placement.city or placement.department

        latitude = (
            float(placement.latitude)
            if placement is not None and placement.latitude is not None
            else None
        )
        longitude = (
            float(placement.longitude)
            if placement is not None and placement.longitude is not None
            else None
        )
        altitude_m = (
            float(placement.altitude_m)
            if placement is not None and placement.altitude_m is not None
            else None
        )

        item = {
            "sensor_pk": sensor.pk,
            "sensor_id": sensor.external_sensor_id,
            "sensor_name": sensor.sensor_name or sensor.external_sensor_id,
            "sensor_detail": sensor.sensor_detail,
            "activity_type": sensor.activity_type,
            "activity_label": activity_label,
            "product_name": sensor.product_name,
            "facility_name": facility.name if facility is not None else "",
            "zone_name": zone.name if zone is not None else "",
            "zone_path": zone.full_name if zone is not None else "",
            "location_label": location_label,
            "city": placement.city if placement is not None else "",
            "department": placement.department if placement is not None else "",
            "latitude": latitude,
            "longitude": longitude,
            "altitude_m": altitude_m,
            "has_location": placement is not None,
            "has_coordinates": latitude is not None and longitude is not None,
        }

        if sensor.external_sensor_id == selected_sensor_id:
            selected = item

        if item["has_coordinates"]:
            map_points.append(
                {
                    **item,
                    "is_selected": sensor.external_sensor_id == selected_sensor_id,
                }
            )

    return {
        "selected": selected,
        "map_points": map_points,
        "visible_count": len(sensors),
        "mapped_count": len(map_points),
        "unmapped_count": len(sensors) - len(map_points),
    }
