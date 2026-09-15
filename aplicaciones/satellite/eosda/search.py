"""EOSDA Search API operations for satellite scenes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from aplicaciones.satellite.eosda.client import EOSDAClient, EOSDARequestError

SENTINEL2_DATASET = "sentinel2"


@dataclass(frozen=True, slots=True)
class EOSDAScene:
    """Normalized scene returned by EOSDA Search API."""

    scene_id: str
    view_id: str
    captured_on: date
    cloud_cover: float | None
    metadata: dict[str, Any]


def build_scene_search_payload(
    *,
    geometry: dict[str, Any],
    date_from: date,
    date_to: date,
    max_cloud_cover: float,
    limit: int = 10,
) -> dict[str, Any]:
    """Build a bounded Sentinel-2 search request for a field polygon."""

    return {
        "fields": [
            "sunElevation",
            "cloudCoverage",
            "sceneID",
            "date",
            "productID",
            "sensor",
            "dataCoveragePercentage",
        ],
        "limit": limit,
        "page": 1,
        "intersection_validation": True,
        "search": {
            "date": {
                "from": date_from.isoformat(),
                "to": date_to.isoformat(),
            },
            "cloudCoverage": {
                "from": 0,
                "to": max_cloud_cover,
            },
            "shapeRelation": "CONTAINS",
            "shape": geometry,
        },
        "sort": {"date": "desc"},
    }


def search_sentinel2_scenes(
    client: EOSDAClient,
    *,
    geometry: dict[str, Any],
    date_from: date,
    date_to: date,
    max_cloud_cover: float = 20,
    limit: int = 10,
) -> list[EOSDAScene]:
    """Search Sentinel-2 scenes that fully cover the requested polygon."""

    payload = build_scene_search_payload(
        geometry=geometry,
        date_from=date_from,
        date_to=date_to,
        max_cloud_cover=max_cloud_cover,
        limit=limit,
    )
    response = client.request_json(
        "POST",
        f"/api/lms/search/v2/{SENTINEL2_DATASET}",
        json=payload,
    )
    if not isinstance(response, dict):
        raise EOSDARequestError("EOSDA returned an invalid scene search response.")

    raw_results = response.get("results")
    if not isinstance(raw_results, list):
        raise EOSDARequestError("EOSDA returned an invalid scene result list.")

    scenes: list[EOSDAScene] = []
    for raw_scene in raw_results:
        if not isinstance(raw_scene, dict):
            continue

        scene_id = str(raw_scene.get("sceneID") or "").strip()
        view_id = str(raw_scene.get("view_id") or "").strip()
        raw_date = str(raw_scene.get("date") or "").strip()
        if not scene_id or not view_id or not raw_date:
            continue

        try:
            captured_on = date.fromisoformat(raw_date[:10])
        except ValueError:
            continue

        raw_cloud_cover = raw_scene.get("cloudCoverage")
        try:
            cloud_cover = (
                float(raw_cloud_cover)
                if raw_cloud_cover is not None
                else None
            )
        except (TypeError, ValueError):
            cloud_cover = None

        scenes.append(
            EOSDAScene(
                scene_id=scene_id,
                view_id=view_id,
                captured_on=captured_on,
                cloud_cover=cloud_cover,
                metadata=dict(raw_scene),
            )
        )

    return scenes
