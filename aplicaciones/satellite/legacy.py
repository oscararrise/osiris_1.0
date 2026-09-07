from __future__ import annotations

import logging

from django.http import HttpResponse
from django.template.loader import render_to_string

from aplicaciones.core.access import accessible_modules

logger = logging.getLogger(__name__)

LEGACY_NDVI_START_MARKER = "            <!-- NDVI -->"
LEGACY_INSERT_MARKER = "            <!-- Control -->"


def _remove_legacy_ndvi_card(html: str) -> str:
    """Remove the obsolete hard-coded NDVI card from the telemetry home."""

    if LEGACY_NDVI_START_MARKER not in html:
        return html
    if LEGACY_INSERT_MARKER not in html:
        logger.warning("Legacy NDVI card found but closing marker is missing")
        return html

    before, remainder = html.split(LEGACY_NDVI_START_MARKER, 1)
    _, after = remainder.split(LEGACY_INSERT_MARKER, 1)
    return f"{before}{LEGACY_INSERT_MARKER}{after}"


def augment_legacy_home_response(request, response: HttpResponse) -> HttpResponse:
    """Replace legacy NDVI with the configurable satellite module card.

    The legacy telemetry dashboard predates the platform module registry and keeps
    a static card grid. This compatibility bridge removes the obsolete NDVI card
    and exposes satellite only through ClientModule/access level, never through a
    client slug or hard-coded tenant rule.
    """

    if getattr(response, "streaming", False):
        return response

    try:
        original_html = response.content.decode(response.charset or "utf-8")
    except (AttributeError, UnicodeDecodeError):
        logger.warning("Could not inspect legacy home response for satellite module injection")
        return response

    html = _remove_legacy_ndvi_card(original_html)
    module = accessible_modules(request.user).filter(code="satellite").first()

    if module is not None:
        if LEGACY_INSERT_MARKER not in html:
            logger.warning("Legacy home marker missing; satellite module card was not injected")
        else:
            card = render_to_string(
                "satellite/_legacy_module_card.html",
                {"module": module},
                request=request,
            )
            html = html.replace(
                LEGACY_INSERT_MARKER,
                f"{card}\n\n{LEGACY_INSERT_MARKER}",
                1,
            )

    if html != original_html:
        response.content = html
        response.headers.pop("Content-Length", None)

    return response
