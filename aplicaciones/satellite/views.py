"""Views for client-scoped satellite monitoring."""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Prefetch, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from aplicaciones.core.access import membership_for
from aplicaciones.core.decorators import module_access_required
from aplicaciones.core.models import AccessLevel
from aplicaciones.satellite.eosda.client import EOSDAError
from aplicaciones.satellite.models import SatelliteField, SatelliteScene
from aplicaciones.satellite.services.fields import register_field_with_eosda
from aplicaciones.satellite.services.scenes import sync_sentinel2_scenes

from .forms import SatelliteFieldForm


@module_access_required("satellite")
def dashboard(request):
    """List and create satellite fields for the authenticated client only."""

    membership = membership_for(request.user)
    if membership is None:
        raise PermissionDenied

    can_manage_fields = membership.access_level >= AccessLevel.OPERATOR

    if request.method == "POST":
        if not can_manage_fields:
            raise PermissionDenied

        form = SatelliteFieldForm(request.POST)
        if form.is_valid():
            field = SatelliteField(
                client=request.client,
                name=form.cleaned_data["name"].strip(),
                crop_type=form.cleaned_data["crop_type"].strip(),
                sowing_date=form.cleaned_data["sowing_date"],
                geometry=form.cleaned_data["coordinates"],
            )
            try:
                field.full_clean()
                field.save()
            except ValidationError as exc:
                for message in exc.messages:
                    form.add_error(None, message)
            else:
                try:
                    register_field_with_eosda(field)
                except EOSDAError:
                    messages.warning(
                        request,
                        (
                            "El lote se guardó en la plataforma, pero EOSDA no pudo "
                            "registrarlo todavía. Las coordenadas no se perdieron y "
                            "podremos reintentar la sincronización."
                        ),
                    )
                else:
                    messages.success(
                        request,
                        f"Lote {field.name} creado y registrado correctamente en EOSDA.",
                    )
                return redirect("satellite:dashboard")
    else:
        form = SatelliteFieldForm()

    scene_queryset = SatelliteScene.objects.order_by("-captured_at")
    fields = (
        SatelliteField.objects.filter(client=request.client)
        .order_by("name")
        .prefetch_related(
            Prefetch(
                "scenes",
                queryset=scene_queryset,
                to_attr="satellite_scenes",
            )
        )
    )
    stats = fields.aggregate(total_area=Sum("area_ha"))

    return render(
        request,
        "satellite/dashboard.html",
        {
            "fields": fields,
            "form": form,
            "can_manage_fields": can_manage_fields,
            "stats": {
                "total": fields.count(),
                "registered": fields.filter(eosda_field_id__isnull=False).count(),
                "pending": fields.filter(eosda_field_id__isnull=True).count(),
                "total_area": stats["total_area"],
            },
        },
    )


@require_POST
@module_access_required("satellite")
def search_field_scenes(request, field_id: int):
    """Search recent Sentinel-2 scenes for one field owned by the current client."""

    membership = membership_for(request.user)
    if membership is None or membership.access_level < AccessLevel.OPERATOR:
        raise PermissionDenied

    field = get_object_or_404(
        SatelliteField,
        pk=field_id,
        client=request.client,
        is_active=True,
    )
    if field.eosda_field_id is None:
        messages.warning(
            request,
            "El lote debe estar sincronizado con EOSDA antes de buscar escenas.",
        )
        return redirect("satellite:dashboard")

    try:
        scenes = sync_sentinel2_scenes(field)
    except EOSDAError:
        messages.error(
            request,
            "EOSDA no pudo completar la búsqueda de escenas en este momento.",
        )
    else:
        if scenes:
            latest = max(scenes, key=lambda scene: scene.captured_at)
            cloud_text = (
                f"{latest.cloud_cover:.1f}% de nubosidad"
                if latest.cloud_cover is not None
                else "nubosidad no informada"
            )
            messages.success(
                request,
                (
                    f"EOSDA encontró {len(scenes)} escena(s) Sentinel-2. "
                    f"La más reciente es del {latest.captured_at:%d/%m/%Y} "
                    f"con {cloud_text}."
                ),
            )
        else:
            messages.warning(
                request,
                "No se encontraron escenas Sentinel-2 recientes para este perímetro.",
            )

    return redirect("satellite:dashboard")
