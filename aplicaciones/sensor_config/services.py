from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import ClientSensor, SensorPlacement, Zone


@transaction.atomic
def assign_sensor_location(
    *,
    sensor: ClientSensor,
    zone: Zone | None = None,
    city: str = "",
    department: str = "",
    latitude: Decimal | None = None,
    longitude: Decimal | None = None,
    altitude_m: Decimal | None = None,
    notes: str = "",
    changed_by=None,
    effective_at=None,
) -> SensorPlacement:
    """Assign a new physical location while preserving placement history.

    The external Aranet database is never written. This service only changes the
    OSIRIS-owned configuration database and atomically closes the previous active
    placement before creating the new one.
    """

    effective_at = effective_at or timezone.now()
    locked_sensor = ClientSensor.objects.select_for_update().get(pk=sensor.pk)

    if zone is not None and zone.client_id != locked_sensor.client_id:
        raise ValidationError(
            {"zone": "La zona debe pertenecer al mismo cliente que el sensor."}
        )

    current = (
        SensorPlacement.objects.select_for_update()
        .filter(sensor=locked_sensor, valid_until__isnull=True)
        .first()
    )
    if current is not None:
        if effective_at <= current.valid_from:
            raise ValidationError(
                {"valid_from": "La nueva ubicación debe iniciar después de la actual."}
            )
        current.valid_until = effective_at
        current.full_clean()
        current.save(update_fields=("valid_until",))

    placement = SensorPlacement(
        sensor=locked_sensor,
        zone=zone,
        city=city.strip()[:120],
        department=department.strip()[:120],
        latitude=latitude,
        longitude=longitude,
        altitude_m=altitude_m,
        valid_from=effective_at,
        notes=notes.strip()[:500],
        created_by=changed_by,
    )
    placement.full_clean()
    placement.save()
    return placement
