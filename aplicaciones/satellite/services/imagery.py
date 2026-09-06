"""Imagery orchestration for persisted satellite scenes."""

from __future__ import annotations

from datetime import timedelta

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


def _latest_imagery_job(scene: SatelliteScene, product: str) -> SatelliteJob | None:
    for job in scene.jobs.filter(job_type=SatelliteJob.JobType.IMAGERY).order_by("-created_at"):
        if job.request_payload.get("product") == product:
            return job
    return None


def imagery_state(scene: SatelliteScene) -> dict[str, dict[str, object]]:
    """Return UI-friendly state for both imagery products without provider calls."""

    assets = scene.assets if isinstance(scene.assets, dict) else {}
    state: dict[str, dict[str, object]] = {}
    for product in SUPPORTED_PRODUCTS:
        asset = assets.get(product) if isinstance(assets.get(product), dict) else None
        job = _latest_imagery_job(scene, product)
        state[product] = {
            "product": product,
            "label": PRODUCT_LABELS[product],
            "asset": asset,
            "job": job,
            "ready": bool(asset and asset.get("url")),
            "waiting": bool(
                job
                and job.status
                in {
                    SatelliteJob.Status.PENDING,
                    SatelliteJob.Status.RUNNING,
                    SatelliteJob.Status.WAITING_PROVIDER,
                }
            ),
            "failed": bool(job and job.status == SatelliteJob.Status.FAILED),
        }
    return state


def request_scene_imagery(
    scene: SatelliteScene,
    *,
    eosda_client: EOSDAClient | None = None,
) -> list[SatelliteJob]:
    """Create Natural Color and NDVI tasks if they are not already ready/in-flight."""

    owns_client = eosda_client is None
    client = eosda_client or EOSDAClient()
    jobs: list[SatelliteJob] = []
    try:
        for product in SUPPORTED_PRODUCTS:
            current = imagery_state(scene)[product]
            if current["ready"] or current["waiting"]:
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
                geometry=scene.field.geometry,
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
