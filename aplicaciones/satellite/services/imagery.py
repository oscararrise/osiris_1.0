"""Imagery orchestration for persisted satellite scenes."""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any

from django.utils import timezone

from aplicaciones.satellite.eosda.client import EOSDAClient
from aplicaciones.satellite.eosda.imagery import (
    PRODUCT_NATURAL_COLOR,
    PRODUCT_NDVI,
    SUPPORTED_PRODUCTS,
    check_visual_task,
    create_visual_task,
)
from aplicaciones.satellite.models import SatelliteJob, SatelliteScene

PRODUCT_LABELS = {
    PRODUCT_NATURAL_COLOR: "Color natural",
    PRODUCT_NDVI: "NDVI",
}

_MIN_CONTEXT_SPAN_METERS = 400.0
_CONTEXT_SCALE = 3.0
_METERS_PER_DEGREE_LAT = 111_320.0


def _latest_imagery_job(scene: SatelliteScene, product: str) -> SatelliteJob | None:
    for job in scene.jobs.filter(job_type=SatelliteJob.JobType.IMAGERY).order_by("-created_at"):
        if job.request_payload.get("product") == product:
            return job
    return None


def build_context_geometry(field_geometry: dict[str, Any]) -> dict[str, Any]:
    """Build a square context window around a field instead of a tight crop."""

    ring = field_geometry["coordinates"][0]
    longitudes = [float(point[0]) for point in ring]
    latitudes = [float(point[1]) for point in ring]

    min_lon, max_lon = min(longitudes), max(longitudes)
    min_lat, max_lat = min(latitudes), max(latitudes)
    center_lon = (min_lon + max_lon) / 2
    center_lat = (min_lat + max_lat) / 2

    meters_per_degree_lon = _METERS_PER_DEGREE_LAT * max(
        math.cos(math.radians(center_lat)),
        0.01,
    )
    width_m = (max_lon - min_lon) * meters_per_degree_lon
    height_m = (max_lat - min_lat) * _METERS_PER_DEGREE_LAT
    target_span_m = max(
        _MIN_CONTEXT_SPAN_METERS,
        width_m * _CONTEXT_SCALE,
        height_m * _CONTEXT_SCALE,
    )

    half_lat = (target_span_m / 2) / _METERS_PER_DEGREE_LAT
    half_lon = (target_span_m / 2) / meters_per_degree_lon
    west = max(-180.0, center_lon - half_lon)
    east = min(180.0, center_lon + half_lon)
    south = max(-90.0, center_lat - half_lat)
    north = min(90.0, center_lat + half_lat)

    return {
        "type": "Polygon",
        "coordinates": [
            [
                [west, south],
                [east, south],
                [east, north],
                [west, north],
                [west, south],
            ]
        ],
    }


def build_overlay_points(
    field_geometry: dict[str, Any],
    context_geometry: dict[str, Any],
) -> str:
    """Convert field coordinates to SVG 0-100 coordinates inside the context image."""

    context_ring = context_geometry["coordinates"][0]
    west = min(float(point[0]) for point in context_ring)
    east = max(float(point[0]) for point in context_ring)
    south = min(float(point[1]) for point in context_ring)
    north = max(float(point[1]) for point in context_ring)
    lon_span = east - west
    lat_span = north - south

    if lon_span <= 0 or lat_span <= 0:
        return ""

    points = []
    for longitude, latitude, *_ in field_geometry["coordinates"][0]:
        x = ((float(longitude) - west) / lon_span) * 100
        y = ((north - float(latitude)) / lat_span) * 100
        points.append(f"{x:.3f},{y:.3f}")
    return " ".join(points)


def imagery_state(scene: SatelliteScene) -> dict[str, dict[str, object]]:
    """Return UI-friendly state for both imagery products without provider calls."""

    assets = scene.assets if isinstance(scene.assets, dict) else {}
    state: dict[str, dict[str, object]] = {}
    for product in SUPPORTED_PRODUCTS:
        asset = assets.get(product) if isinstance(assets.get(product), dict) else None
        job = _latest_imagery_job(scene, product)
        waiting = bool(
            job
            and job.status
            in {
                SatelliteJob.Status.PENDING,
                SatelliteJob.Status.RUNNING,
                SatelliteJob.Status.WAITING_PROVIDER,
            }
        )
        has_asset = bool(asset and asset.get("url"))
        state[product] = {
            "product": product,
            "label": PRODUCT_LABELS[product],
            "asset": asset,
            "job": job,
            "has_asset": has_asset,
            "ready": bool(has_asset and not waiting),
            "waiting": waiting,
            "failed": bool(job and job.status == SatelliteJob.Status.FAILED),
        }
    return state


def request_scene_imagery(
    scene: SatelliteScene,
    *,
    eosda_client: EOSDAClient | None = None,
    force: bool = False,
) -> list[SatelliteJob]:
    """Create contextual Natural Color and NDVI tasks for one scene."""

    owns_client = eosda_client is None
    client = eosda_client or EOSDAClient()
    jobs: list[SatelliteJob] = []
    context_geometry = build_context_geometry(scene.field.geometry)
    overlay_points = build_overlay_points(scene.field.geometry, context_geometry)

    try:
        for product in SUPPORTED_PRODUCTS:
            current = imagery_state(scene)[product]
            if current["waiting"]:
                if current["job"] is not None:
                    jobs.append(current["job"])
                continue
            if current["ready"] and not force:
                if current["job"] is not None:
                    jobs.append(current["job"])
                continue

            reference = (
                f"osiris-{scene.field_id}-{scene.id}-{product}-"
                f"{timezone.now():%Y%m%d%H%M%S}"
            )
            task = create_visual_task(
                client,
                view_id=scene.view_id,
                geometry=context_geometry,
                product=product,
                reference=reference,
                px_size=4,
            )
            job = SatelliteJob.objects.create(
                field=scene.field,
                scene=scene,
                job_type=SatelliteJob.JobType.IMAGERY,
                status=SatelliteJob.Status.WAITING_PROVIDER,
                provider_task_id=task.task_id,
                attempts=0,
                next_check_at=timezone.now() + timedelta(seconds=5),
                request_payload={
                    "product": product,
                    "reference": reference,
                    "view_id": scene.view_id,
                    "context_geometry": context_geometry,
                    "overlay_points": overlay_points,
                },
                result_payload=task.payload,
                started_at=timezone.now(),
            )
            jobs.append(job)
    finally:
        if owns_client:
            client.close()
    return jobs


def refresh_scene_imagery(
    scene: SatelliteScene,
    *,
    eosda_client: EOSDAClient | None = None,
) -> list[SatelliteJob]:
    """Poll active EOSDA imagery tasks once and persist ready asset URLs."""

    owns_client = eosda_client is None
    client = eosda_client or EOSDAClient()
    updated: list[SatelliteJob] = []
    try:
        for product in SUPPORTED_PRODUCTS:
            job = _latest_imagery_job(scene, product)
            if job is None or not job.provider_task_id:
                continue
            if job.status in {SatelliteJob.Status.COMPLETED, SatelliteJob.Status.FAILED}:
                continue

            status = check_visual_task(client, job.provider_task_id)
            job.attempts += 1
            job.result_payload = status.payload

            if status.is_failed:
                job.status = SatelliteJob.Status.FAILED
                job.error_message = "EOSDA reported an imagery task failure."
                job.finished_at = timezone.now()
                job.next_check_at = None
            elif status.is_finished and status.image_url:
                assets = dict(scene.assets or {})
                assets[product] = {
                    "url": status.image_url,
                    "generated_at": timezone.now().isoformat(),
                    "provider_task_id": job.provider_task_id,
                    "context_geometry": job.request_payload.get("context_geometry"),
                    "overlay_points": job.request_payload.get("overlay_points", ""),
                }
                scene.assets = assets
                scene.save(update_fields=("assets", "updated_at"))
                job.status = SatelliteJob.Status.COMPLETED
                job.finished_at = timezone.now()
                job.next_check_at = None
                job.error_message = ""
            else:
                job.status = SatelliteJob.Status.WAITING_PROVIDER
                job.next_check_at = timezone.now() + timedelta(seconds=10)

            job.save(
                update_fields=(
                    "status",
                    "attempts",
                    "next_check_at",
                    "result_payload",
                    "error_message",
                    "finished_at",
                    "updated_at",
                )
            )
            updated.append(job)
    finally:
        if owns_client:
            client.close()
    return updated
