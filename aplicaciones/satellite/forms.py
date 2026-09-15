"""Forms for satellite field management."""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from .models import validate_polygon_geojson


class SatelliteFieldForm(forms.Form):
    """Collect a client lot without exposing tenant ownership in the browser."""

    name = forms.CharField(
        label="Nombre del lote",
        max_length=160,
        widget=forms.TextInput(attrs={"placeholder": "Ej. Lote Norte"}),
    )
    crop_type = forms.CharField(
        label="Cultivo",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Ej. Arándano"}),
    )
    sowing_date = forms.DateField(
        label="Fecha de siembra",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    coordinates = forms.CharField(
        label="Perímetro del lote",
        help_text="Una coordenada por línea en formato longitud,latitud.",
        widget=forms.Textarea(
            attrs={
                "rows": 8,
                "placeholder": "-74.1000,4.6000\n-74.0900,4.6000\n-74.0900,4.5900",
                "spellcheck": "false",
            }
        ),
    )

    def clean_coordinates(self) -> dict[str, object]:
        raw = self.cleaned_data["coordinates"]
        points: list[list[float]] = []

        for line_number, raw_line in enumerate(raw.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 2:
                raise ValidationError(
                    f"Línea {line_number}: use exactamente longitud,latitud."
                )
            try:
                longitude = float(parts[0])
                latitude = float(parts[1])
            except ValueError as exc:
                raise ValidationError(
                    f"Línea {line_number}: longitud y latitud deben ser numéricas."
                ) from exc
            points.append([longitude, latitude])

        if len(points) < 3:
            raise ValidationError("Ingrese al menos tres vértices para formar el lote.")
        if len({(point[0], point[1]) for point in points}) < 3:
            raise ValidationError("El lote debe contener al menos tres vértices diferentes.")
        if points[0] != points[-1]:
            points.append(points[0].copy())

        geometry: dict[str, object] = {"type": "Polygon", "coordinates": [points]}
        validate_polygon_geojson(geometry)
        return geometry
