from __future__ import annotations

from django import forms

from .models import Zone


class SensorLocationForm(forms.Form):
    facility_type = forms.ChoiceField(
        label="Tipo de ubicación principal",
        choices=(
            (Zone.ZoneType.FARM, "Finca"),
            (Zone.ZoneType.GREENHOUSE, "Invernadero"),
        ),
    )
    facility_name = forms.CharField(
        label="Finca / Invernadero",
        max_length=160,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Ej. Finca La Esperanza",
                "autocomplete": "off",
                "list": "facility-options",
            }
        ),
    )
    zone_name = forms.CharField(
        label="Zona",
        max_length=160,
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Ej. Sector A1, Cuarto frío 2",
                "autocomplete": "off",
                "list": "zone-options",
            }
        ),
    )
    city = forms.CharField(
        label="Ciudad",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Ej. Bogotá"}),
    )
    department = forms.CharField(
        label="Departamento",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Ej. Cundinamarca"}),
    )
    latitude = forms.DecimalField(
        label="Latitud",
        max_digits=10,
        decimal_places=7,
        min_value=-90,
        max_value=90,
        required=False,
        widget=forms.NumberInput(attrs={"step": "0.0000001", "placeholder": "4.6872531"}),
    )
    longitude = forms.DecimalField(
        label="Longitud",
        max_digits=10,
        decimal_places=7,
        min_value=-180,
        max_value=180,
        required=False,
        widget=forms.NumberInput(attrs={"step": "0.0000001", "placeholder": "-74.0628734"}),
    )
    altitude_m = forms.DecimalField(
        label="Altura (m s. n. m.)",
        max_digits=8,
        decimal_places=2,
        min_value=-1000,
        max_value=10000,
        required=False,
        widget=forms.NumberInput(attrs={"step": "0.01", "placeholder": "2630"}),
    )
    notes = forms.CharField(
        label="Notas",
        max_length=500,
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Referencia física, responsable, observaciones de instalación...",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        latitude = cleaned_data.get("latitude")
        longitude = cleaned_data.get("longitude")
        if (latitude is None) != (longitude is None):
            message = "Latitud y longitud deben registrarse juntas."
            self.add_error("latitude", message)
            self.add_error("longitude", message)
        return cleaned_data
