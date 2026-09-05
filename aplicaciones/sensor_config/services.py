from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from aplicaciones.core.models import Client

from .models import ClientSensor, SensorPlacement, Zone


@dataclass(frozen=True)
class SensorSyncResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    deactivated: int = 0
    skipped: int = 0

    @property
    def total_seen(self) -> int:
        return self.created + self.updated + self.unchanged


def _external_sensor_detail(row: dict[str, Any]) -> str:
    type_name = str(row.get("type_name") or "").strip()
    code = str(row.get("code") or "").strip()
    parts: list[str] = []
    if type_name:
        parts.append(type_name)
    if code:
        parts.append(f"Código {code}")
    return " · ".join(parts)[:500]


@transaction.atomic
def sync_sensor_snapshot(
    *,
    client: Client,
    sensor_rows: Iterable[dict[str, Any]],
    dry_run: bool = False,
) -> SensorSyncResult:
    """Mirror an authoritative external sensor snapshot into OSIRIS.

    The external database remains read-only. Sensors are identified by the pair
    ``client + external_sensor_id``. Missing sensors are deactivated rather than
    deleted so placement history remains intact.
    """

    existing = {
        sensor.external_sensor_id: sensor
        for sensor in ClientSensor.objects.select_for_update().filter(client=client)
    }
    seen_ids: set[str] = set()
    created = updated = unchanged = skipped = 0

    for row in sensor_rows:
        external_sensor_id = str(row.get("id") or "").strip()
        if not external_sensor_id:
            skipped += 1
            continue

        seen_ids.add(external_sensor_id)
        sensor_name = str(
            row.get("name") or row.get("code") or external_sensor_id
        ).strip()[:200]
        sensor_detail = _external_sensor_detail(row)
        external_is_active = bool(row.get("is_active", True))

        sensor = existing.get(external_sensor_id)
        if sensor is None:
            created += 1
            if not dry_run:
                ClientSensor.objects.create(
                    client=client,
                    external_sensor_id=external_sensor_id,
                    sensor_name=sensor_name,
                    sensor_detail=sensor_detail,
                    is_active=external_is_active,
                )
            continue

        changed_fields: list[str] = []
        desired_values = {
            "sensor_name": sensor_name,
            "sensor_detail": sensor_detail,
            "is_active": external_is_active,
        }
        for field, value in desired_values.items():
            if getattr(sensor, field) != value:
                setattr(sensor, field, value)
                changed_fields.append(field)

        if not changed_fields:
            unchanged += 1
            continue

        updated += 1
        if not dry_run:
            sensor.save(update_fields=(*changed_fields, "updated_at"))

    active_missing = [
        sensor
        for external_sensor_id, sensor in existing.items()
        if external_sensor_id not in seen_ids and sensor.is_active
    ]
    deactivated = len(active_missing)
    if not dry_run and active_missing:
        ClientSensor.objects.filter(pk__in=[sensor.pk for sensor in active_missing]).update(
            is_active=False,
            updated_at=timezone.now(),
        )

    return SensorSyncResult(
        created=created,
        updated=updated,
        unchanged=unchanged,
        deactivated=deactivated,
        skipped=skipped,
    )


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
