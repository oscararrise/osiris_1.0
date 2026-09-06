"""EOSDA Imagery API operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from aplicaciones.satellite.eosda.client import EOSDAClient, EOSDARequestError

IMAGERY_ENDPOINT = "/api/gdw/api"

PRODUCT_NATURAL_COLOR = "natural_color"
PRODUCT_NDVI = "ndvi"
SUPPORTED_PRODUCTS = (PRODUCT_NATURAL_COLOR, PRODUCT_NDVI)

_PRODUCT_SETTINGS = {
    PRODUCT_NATURAL_COLOR: {
        "bm_type": "B04,B03,B02",
        "name_alias": "NATURAL_COLOR",
    },
    PRODUCT_NDVI: {
        "bm_type": "NDVI",
        "name_alias": "NDVI",
    },
}


@dataclass(frozen=True, slots=True)
class EOSDAImageryTask:
    task_id: str
    status: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class EOSDAImageryStatus:
    status: str
    payload: dict[str, Any]
    image_url: str = ""

    @property
    def is_finished(self) -> bool:
        return self.status == "finished"

    @property
    def is_failed(self) -> bool:
        return self.status in {"failed", "error"}


def build_visual_payload(
    *,
    view_id: str,
    geometry: dict[str, Any],
    product: str,
    reference: str,
    px_size: int = 4,
) -> dict[str, Any]:
    """Build a bounded PNG visualization task for one Sentinel-2 scene."""

    if product not in _PRODUCT_SETTINGS:
        raise ValueError(f"Unsupported imagery product: {product}")

    settings = _PRODUCT_SETTINGS[product]
    return {
        "type": "jpeg",
        "params": {
            "view_id": view_id,
            "bm_type": settings["bm_type"],
            "name_alias": settings["name_alias"],
            "geometry": geometry,
            "px_size": px_size,
            "format": "png",
            "reference": reference,
            "calibrate": 1,
        },
    }


def create_visual_task(
    client: EOSDAClient,
    *,
    view_id: str,
    geometry: dict[str, Any],
    product: str,
    reference: str,
    px_size: int = 4,
) -> EOSDAImageryTask:
    payload = build_visual_payload(
        view_id=view_id,
        geometry=geometry,
        product=product,
        reference=reference,
        px_size=px_size,
    )
    response = client.request_json("POST", IMAGERY_ENDPOINT, json=payload)
    if not isinstance(response, dict):
        raise EOSDARequestError("EOSDA returned an invalid imagery task response.")

    task_id = str(response.get("task_id") or "").strip()
    status = str(response.get("status") or "created").strip().lower()
    if not task_id:
        raise EOSDARequestError("EOSDA returned an imagery task without task_id.")

    return EOSDAImageryTask(task_id=task_id, status=status, payload=response)


def _find_https_url(value: Any) -> str:
    """Find the first HTTPS URL in the provider result without trusting key names."""

    if isinstance(value, str):
        parsed = urlparse(value)
        if parsed.scheme == "https" and parsed.netloc:
            return value
        return ""
    if isinstance(value, dict):
        preferred_keys = (
            "url",
            "download_url",
            "downloadUrl",
            "file_url",
            "fileUrl",
            "image_url",
            "imageUrl",
            "result",
        )
        for key in preferred_keys:
            if key in value:
                found = _find_https_url(value[key])
                if found:
                    return found
        for item in value.values():
            found = _find_https_url(item)
            if found:
                return found
        return ""
    if isinstance(value, list):
        for item in value:
            found = _find_https_url(item)
            if found:
                return found
    return ""


def check_visual_task(client: EOSDAClient, task_id: str) -> EOSDAImageryStatus:
    response = client.request_json("GET", f"{IMAGERY_ENDPOINT}/{task_id}")
    if not isinstance(response, dict):
        raise EOSDARequestError("EOSDA returned an invalid imagery status response.")

    status = str(response.get("status") or "").strip().lower()
    if not status:
        if response.get("errors"):
            status = "failed"
        elif response.get("result"):
            status = "finished"
        else:
            status = "started"

    return EOSDAImageryStatus(
        status=status,
        payload=response,
        image_url=_find_https_url(response),
    )
