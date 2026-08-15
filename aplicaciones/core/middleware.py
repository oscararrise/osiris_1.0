from __future__ import annotations

from zoneinfo import ZoneInfo

from django.utils import timezone

from .access import membership_for


class ClientContextMiddleware:
    """Attach the authenticated user's only client to every request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.client_membership = membership_for(request.user)
        request.client = (
            request.client_membership.client if request.client_membership is not None else None
        )
        if request.client is not None:
            timezone.activate(ZoneInfo(request.client.timezone))
        else:
            timezone.deactivate()
        return self.get_response(request)
