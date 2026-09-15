from __future__ import annotations

from .access import accessible_modules


def client_context(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"current_client": None, "available_modules": ()}
    return {
        "current_client": getattr(request, "client", None),
        "available_modules": accessible_modules(request.user),
    }
