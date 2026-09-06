"""EOSDA Field Management operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from aplicaciones.satellite.eosda.client import EOSDAClient, EOSDARequestError


@dataclass(frozen=True, slots=True)
class EOSDACreatedField:
    """Normalized response returned after creating an EOSDA field."""

    field_id: int
    area_ha: Decimal


def build_create_field_payload(
    *,
    name: str,
    geometry: dict[str, Any],
    group: str = "",
    crop_type: str = "",
    sowing_date: date | None = None,
) -> dict[str, Any]:
    """Build the GeoJSON Feature expected by EOSDA Field Management."""

    properties: dict[str, Any] = {"name": name}
    if group:
        properties["group"] = group

    crop_period: dict[str, Any] = {}
    if crop_type:
        crop_period["crop_type"] = crop_type
    if sowing_date is not None:
        crop_period["year"] = sowing_date.year
        crop_period["sowing_date"] = sowing_date.isoformat()
    if crop_period:
        properties["years_data"] = [crop_period]

    return {
        "type": "Feature",
        "properties": properties,
        "geometry": geometry,
    }


def create_field(
    client: EOSDAClient,
    *,
    name: str,
    geometry: dict[str, Any],
    group: str = "",
    crop_type: str = "",
    sowing_date: date | None = None,
) -> EOSDACreatedField:
    """Create a field in EOSDA and normalize its identifier and area."""

    payload = build_create_field_payload(
        name=name,
        geometry=geometry,
        group=group,
        crop_type=crop_type,
        sowing_date=sowing_date,
    )
    response = client.request_json("POST", "/field-management", json=payload)
    if not isinstance(response, dict):
        raise EOSDARequestError("EOSDA returned an invalid field creation response.")

    raw_field_id = response.get("id")
    if isinstance(raw_field_id, bool):
        raise EOSDARequestError("EOSDA returned an invalid field id.")
    try:
        field_id = int(raw_field_id)
    except (TypeError, ValueError) as exc:
        raise EOSDARequestError("EOSDA returned an invalid field id.") from exc
    if field_id <= 0:
        raise EOSDARequestError("EOSDA returned an invalid field id.")

    try:
        area_ha = Decimal(str(response.get("area")))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise EOSDARequestError("EOSDA returned an invalid field area.") from exc
    if area_ha <= 0:
        raise EOSDARequestError("EOSDA returned an invalid field area.")

    return EOSDACreatedField(field_id=field_id, area_ha=area_ha)
