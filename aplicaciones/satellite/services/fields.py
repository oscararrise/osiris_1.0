"""Satellite field registration services."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils import timezone

from aplicaciones.satellite.eosda.client import EOSDAClient
from aplicaciones.satellite.eosda.fields import create_field as create_eosda_field
from aplicaciones.satellite.models import SatelliteField


def register_field_with_eosda(
    field: SatelliteField,
    *,
    eosda_client: EOSDAClient | None = None,
) -> SatelliteField:
    """Register a saved local field in EOSDA and persist provider metadata.

    The local field is intentionally saved first. If EOSDA is unavailable, the
    client/lot relationship and polygon remain safely stored in OSIRIS and can be
    retried later.

    Local crop labels are intentionally not sent during field creation. EOSDA
    accepts only provider-defined crop types while OSIRIS keeps ``crop_type`` as
    client-owned free text. Crop-period metadata will be synchronized separately
    after mapping it to an EOSDA-supported value, so an arbitrary local label can
    never block the geographic field registration.
    """

    if field.pk is None:
        raise ValidationError("El lote debe guardarse localmente antes de registrarlo en EOSDA.")
    if field.eosda_field_id is not None:
        return field

    field.full_clean()

    owns_client = eosda_client is None
    client = eosda_client or EOSDAClient()
    try:
        created = create_eosda_field(
            client,
            name=field.name,
            geometry=field.geometry,
            group=field.client.slug,
        )
    finally:
        if owns_client:
            client.close()

    field.eosda_field_id = created.field_id
    field.area_ha = created.area_ha
    field.last_sync_at = timezone.now()
    field.save(update_fields=("eosda_field_id", "area_ha", "last_sync_at", "updated_at"))
    return field
