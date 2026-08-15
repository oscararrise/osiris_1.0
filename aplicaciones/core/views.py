from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .access import accessible_modules, membership_for


def root(request):
    return redirect("inicio" if request.user.is_authenticated else "login")


@login_required
def operations(request):
    membership = membership_for(request.user)
    return render(
        request,
        "core/operations.html",
        {"membership": membership, "modules": accessible_modules(request.user)},
    )
