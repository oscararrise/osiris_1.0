from __future__ import annotations

from zoneinfo import ZoneInfo

from django.utils import timezone

from aplicaciones.automatizacion.telemetry_cache import (
    reset_telemetry_database_alias,
    set_telemetry_database_alias,
)

from .access import membership_for
from .models import ClientDataSource


class ClientContextMiddleware:
    """Attach the authenticated user's only client to every request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.client_membership = membership_for(request.user)
        request.client = (
            request.client_membership.client if request.client_membership is not None else None
        )

        telemetry_token = None
        data_source = getattr(request.client, "data_source", None) if request.client else None

        if request.client is not None:
            timezone.activate(ZoneInfo(request.client.timezone))
        else:
            timezone.deactivate()

        if (
            data_source is not None
            and data_source.is_active
            and data_source.adapter_key == ClientDataSource.Adapter.TELEMETRY
        ):
            telemetry_token = set_telemetry_database_alias(data_source.database_alias)

        try:
            return self.get_response(request)
        finally:
            if telemetry_token is not None:
                reset_telemetry_database_alias(telemetry_token)
