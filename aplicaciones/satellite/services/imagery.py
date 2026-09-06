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

VIEW_CONTEXT = "context"
VIEW_DETAIL = "detail"
VIEW_PRESETS = {
    VIEW_CONTEXT: {
        "label": "Contexto",
        "min_span_m": 400.0,
        "scale": 3.0,
        "preferred_px_size": 4,
    },
    VIEW_DETAIL: {
        "label": "Detalle",
        "min_span_m": 150.0,
        "scale": 2.0,
        "preferred_px_size": 1,
    },
}

_METERS_PER_DEGREE_LAT = 111_320.0
_MAX_OUTPUT_PIXELS = 1024
_ACTIVE_JOB_STATUSES = {
    SatelliteJob.Status.PENDING,
    SatelliteJob.Status.RUNNING,
    SatelliteJob.Status.WAITING_PROVIDER,
}


def _geometry_bounds(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    ring = geometry["coordinates"][0]
    longitudes = [float(point[0]) for point in ring]
    latitudes = [float(point[1]) for point in ring]
    return min(longitudes), max(longitudes), min(latitudes), max(latitudes)


def _meters_per_degree_lon(latitude: float) -> float:
    return _METERS_PER_DEGREE_LAT * max(math.cos(math.radians(latitude)), 0.01)


def _geometry_span_m(geometry: dict[str, Any]) -> float:
    min_lon, max_lon, min_lat, max_lat = _geometry_bounds(geometry)
    center_lat = (min_lat + max_lat) / 2
    width_m = (max_lon - min_lon) * _meters_per_degree_lon(center_lat)
    height_m = (max_lat - min_lat) * _METERS_PER_DEGREE_LAT
    return max(width_m, height_m)


def build_view_geometry(
    field_geometry: dict[str, Any],
    *,
    min_span_m: float,
    scale: float,
) -> dict[str, Any]:
    """Build a square view window around a field for imagery rendering."""

    min_lon, max_lon, min_lat, max_lat = _geometry_bounds(field_geometry)
    center_lon = (min_lon + max_lon) / 2
    center_lat = (min_lat + max_lat) / 2
    meters_per_degree_lon = _meters_per_degree_lon(center_lat)

    width_m = (max_lon - min_lon) * meters_per_degree_lon
    height_m = (max_lat - min_lat) * _METERS_PER_DEGREE_LAT
    target_span_m = max(
        min_span_m,
        width_m * scale,
        height_m * scale,
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


def build_context_geometry(field_geometry: dict[str, Any]) -> dict[str, Any]:
    """Build the wider operational context around a field."""

    preset = VIEW_PRESETS[VIEW_CONTEXT]
    return build_view_geometry(
        field_geometry,
        min_span_m=float(preset["min_span_m"]),
        scale=float(preset["scale"]),
    )


def build_detail_geometry(field_geometry: dict[str, Any]) -> dict[str, Any]:
    """Build a closer view around a field while retaining nearby context."""

    preset = VIEW_PRESETS[VIEW_DETAIL]
    return build_view_geometry(
        field_geometry,
        min_span_m=float(preset["min_span_m"]),
        scale=float(preset["scale"]),
    )


def build_overlay_points(
    field_geometry: dict[str, Any],
    view_geometry: dict[str, Any],
) -> str:
    """Convert field coordinates to SVG 0-100 coordinates inside a rendered view."""

    view_ring = view_geometry["coordinates"][0]
    west = min(float(point[0]) for point in view_ring)
    east = max(float(point[0]) for point in view_ring)
    south = min(float(point[1]) for point in view_ring)
    north = max(float(point[1]) for point in view_ring)
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


def _effective_px_size(view_geometry: dict[str, Any], preferred_px_size: int) -> int:
    """Keep provider output bounded while allowing finer small-field detail views."""

    span_m = _geometry_span_m(view_geometry)
    bounded_px_size = math.ceil(span_m / _MAX_OUTPUT_PIXELS)
    return max(int(preferred_px_size), bounded_px_size, 1)


def _job_view_mode(job: SatelliteJob) -> str:
    view_mode = str(job.request_payload.get("view_mode") or VIEW_CONTEXT)
    return view_mode if view_mode in VIEW_PRESETS else VIEW_CONTEXT


def _latest_imagery_job(
    scene: SatelliteScene,
    product: str,
    view_mode: str,
) -> SatelliteJob | None:
    for job in scene.jobs.filter(job_type=SatelliteJob.JobType.IMAGERY).order_by("-created_at"):
        if (
            job.request_payload.get("product") == product
            and _job_view_mode(job) == view_mode
        ):
            return job
    return None


def _product_assets(scene: SatelliteScene, product: str) -> dict[str, dict[str, Any]]:
    """Normalize old single-asset rows into the new context/detail structure."""

    assets = scene.assets if isinstance(scene.assets, dict) else {}
    raw_product = assets.get(product)
    if not isinstance(raw_product, dict):
        return {}

    if raw_product.get("url"):
        return {VIEW_CONTEXT: raw_product}

    normalized: dict[str, dict[str, Any]] = {}
    for view_mode in VIEW_PRESETS:
        candidate = raw_product.get(view_mode)
        if isinstance(candidate, dict):
            normalized[view_mode] = candidate
    return normalized


def _variant_state(
    scene: SatelliteScene,
    product: str,
    view_mode: str,
) -> dict[str, object]:
    asset = _product_assets(scene, product).get(view_mode)
    job = _latest_imagery_job(scene, product, view_mode)
    waiting = bool(job and job.status in _ACTIVE_JOB_STATUSES)
    has_asset = bool(asset and asset.get("url"))
    return {
        "view_mode": view_mode,
        "label": VIEW_PRESETS[view_mode]["label"],
        "asset": asset,
        "job": job,
        "has_asset": has_asset,
        "ready": bool(has_asset and not waiting),
        "waiting": waiting,
        "failed": bool(job and job.status == SatelliteJob.Status.FAILED),
    }


def imagery_state(scene: SatelliteScene) -> dict[str, dict[str, object]]:
    """Return UI-friendly state for context and detail imagery products."""

    state: dict[str, dict[str, object]] = {}
    for product in SUPPORTED_PRODUCTS:
        context = _variant_state(scene, product, VIEW_CONTEXT)
        detail = _variant_state(scene, product, VIEW_DETAIL)
        state[product] = {
            "product": product,
            "label": PRODUCT_LABELS[product],
            VIEW_CONTEXT: context,
            VIEW_DETAIL: detail,
            "preferred": detail if detail["has_asset"] else context,
        }
    return state


def request_scene_imagery(
    scene: SatelliteScene,
    *,
    eosda_client: EOSDAClient | None = None,
    view_mode: str = VIEW_CONTEXT,
    force: bool = False,
) -> list[SatelliteJob]:
    """Create Natural Color and NDVI tasks for one scene and one view mode."""

    if view_mode not in VIEW_PRESETS:
        raise ValueError(f"Unsupported imagery view mode: {view_mode}")

    owns_client = eosda_client is None
    client = eosda_client or EOSDAClient()
    jobs: list[SatelliteJob] = []
    preset = VIEW_PRESETS[view_mode]
    view_geometry = build_view_geometry(
        scene.field.geometry,
        min_span_m=float(preset["min_span_m"]),
        scale=float(preset["scale"]),
    )
    overlay_points = build_overlay_points(scene.field.geometry, view_geometry)
    px_size = _effective_px_size(
        view_geometry,
        int(preset["preferred_px_size"]),
    )

    try:
        for product in SUPPORTED_PRODUCTS:
            current = imagery_state(scene)[product][view_mode]
            if current["waiting"]:
                if current["job"] is not None:
                    jobs.append(current["job"])
                continue
            if current["ready"] and not force:
                if current["job"] is not None:
                    jobs.append(current["job"])
                continue

            reference = (
                f"osiris-{scene.field_id}-{scene.id}-{product}-{view_mode}-"
                f"{timezone.now():%Y%m%d%H%M%S}"
            )
            task = create_visual_task(
                client,
                view_id=scene.view_id,
                geometry=view_geometry,
                product=product,
                reference=reference,
                px_size=px_size,
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
                    "view_mode": view_mode,
                    "view_geometry": view_geometry,
                    "overlay_points": overlay_points,
                    "px_size": px_size,
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
        for view_mode in VIEW_PRESETS:
            for product in SUPPORTED_PRODUCTS:
                job = _latest_imagery_job(scene, product, view_mode)
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
                    product_assets = _product_assets(scene, product)
                    product_assets[view_mode] = {
                        "url": status.image_url,
                        "generated_at": timezone.now().isoformat(),
                        "provider_task_id": job.provider_task_id,
                        "view_mode": view_mode,
                        "view_geometry": job.request_payload.get("view_geometry"),
                        "overlay_points": job.request_payload.get("overlay_points", ""),
                        "px_size": job.request_payload.get("px_size"),
                    }
                    assets[product] = product_assets
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
