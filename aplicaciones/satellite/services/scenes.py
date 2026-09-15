"""Scene synchronization services for satellite fields."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.utils import timezone

from aplicaciones.satellite.eosda.client import EOSDAClient
from aplicaciones.satellite.eosda.search import (
    SENTINEL2_DATASET,
    EOSDAScene,
    search_sentinel2_scenes,
)
from aplicaciones.satellite.models import SatelliteField, SatelliteScene


def _captured_at(scene: EOSDAScene):
    current_timezone = timezone.get_current_timezone()
    return timezone.make_aware(
        datetime.combine(scene.captured_on, time.min),
        current_timezone,
    )


def sync_sentinel2_scenes(
    field: SatelliteField,
    *,
    eosda_client: EOSDAClient | None = None,
    lookback_days: int = 180,
    preferred_cloud_cover: float = 20,
    fallback_cloud_cover: float = 50,
    limit: int = 10,
) -> list[SatelliteScene]:
    """Search and persist recent Sentinel-2 scenes for one client-owned field.

    A strict low-cloud search is attempted first. If EOSDA returns no scenes,
    the threshold is relaxed once so cloudy regions still have a usable result.
    """

    field.full_clean()

    date_to = timezone.localdate()
    date_from = date_to - timedelta(days=max(1, lookback_days) - 1)

    owns_client = eosda_client is None
    client = eosda_client or EOSDAClient()
    try:
        scenes = search_sentinel2_scenes(
            client,
            geometry=field.geometry,
            date_from=date_from,
            date_to=date_to,
            max_cloud_cover=preferred_cloud_cover,
            limit=limit,
        )
        if not scenes and fallback_cloud_cover > preferred_cloud_cover:
            scenes = search_sentinel2_scenes(
                client,
                geometry=field.geometry,
                date_from=date_from,
                date_to=date_to,
                max_cloud_cover=fallback_cloud_cover,
                limit=limit,
            )
    finally:
        if owns_client:
            client.close()

    persisted: list[SatelliteScene] = []
    for scene in scenes:
        stored, _ = SatelliteScene.objects.update_or_create(
            field=field,
            dataset=SENTINEL2_DATASET,
            view_id=scene.view_id,
            defaults={
                "provider": SatelliteScene.Provider.EOSDA,
                "captured_at": _captured_at(scene),
                "cloud_cover": scene.cloud_cover,
                "metadata": scene.metadata,
            },
        )
        persisted.append(stored)

    return persisted
