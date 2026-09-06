from __future__ import annotations

import logging

from django.http import HttpResponse
from django.template.loader import render_to_string

from aplicaciones.core.access import accessible_modules

logger = logging.getLogger(__name__)

LEGACY_INSERT_MARKER = "            <!-- Control -->"


def augment_legacy_home_response(request, response: HttpResponse) -> HttpResponse:
    """Inject the satellite card into the legacy home when access is enabled.

    The legacy telemetry dashboard predates the platform module registry and keeps
    a static card grid. This compatibility bridge preserves that UI while making
    satellite visibility depend on ClientModule/access level, never on a client
    slug or hard-coded tenant rule.
    """

    module = accessible_modules(request.user).filter(code="satellite").first()
    if module is None or getattr(response, "streaming", False):
        return response

    try:
        html = response.content.decode(response.charset or "utf-8")
    except (AttributeError, UnicodeDecodeError):
        logger.warning("Could not inspect legacy home response for satellite module injection")
        return response

    if LEGACY_INSERT_MARKER not in html:
        logger.warning("Legacy home marker missing; satellite module card was not injected")
        return response

    card = render_to_string(
        "satellite/_legacy_module_card.html",
        {"module": module},
        request=request,
    )
    response.content = html.replace(
        LEGACY_INSERT_MARKER,
        f"{card}\n\n{LEGACY_INSERT_MARKER}",
        1,
    )
    response.headers.pop("Content-Length", None)
    return response
