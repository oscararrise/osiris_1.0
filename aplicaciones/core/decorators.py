from __future__ import annotations

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .access import can_access_module


def module_access_required(module_code: str):
    """Protect a module even when a user enters its URL directly."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not can_access_module(request.user, module_code):
                raise PermissionDenied("Este módulo no está habilitado para tu cuenta.")
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
