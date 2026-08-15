from __future__ import annotations

from django.db.models import QuerySet

from .models import ClientMembership, ClientModule, PlatformModule


def membership_for(user) -> ClientMembership | None:
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        membership = user.client_membership
    except ClientMembership.DoesNotExist:
        return None
    if not membership.is_active or not membership.client.is_active:
        return None
    return membership


def accessible_modules(user) -> QuerySet[PlatformModule]:
    membership = membership_for(user)
    if membership is None:
        return PlatformModule.objects.none()
    return PlatformModule.objects.filter(
        is_active=True,
        client_settings__client=membership.client,
        client_settings__is_enabled=True,
        client_settings__minimum_access_level__lte=membership.access_level,
    ).distinct()


def can_access_module(user, module_code: str) -> bool:
    membership = membership_for(user)
    if membership is None:
        return False
    return ClientModule.objects.filter(
        client=membership.client,
        module__code=module_code,
        module__is_active=True,
        is_enabled=True,
        minimum_access_level__lte=membership.access_level,
    ).exists()
