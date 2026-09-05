from django.contrib import admin

from .models import ClientSensor, SensorPlacement, Zone


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "zone_type", "client", "parent", "is_active")
    list_filter = ("client", "zone_type", "is_active")
    search_fields = ("name", "code", "client__name")
    autocomplete_fields = ("parent",)


@admin.register(ClientSensor)
class ClientSensorAdmin(admin.ModelAdmin):
    list_display = (
        "external_sensor_id",
        "sensor_name",
        "sensor_detail",
        "client",
        "is_active",
    )
    list_filter = ("client", "is_active")
    search_fields = (
        "external_sensor_id",
        "sensor_name",
        "sensor_detail",
        "client__name",
    )


@admin.register(SensorPlacement)
class SensorPlacementAdmin(admin.ModelAdmin):
    list_display = (
        "sensor",
        "facility_name",
        "zone",
        "city",
        "department",
        "latitude",
        "longitude",
        "altitude_m",
        "valid_from",
        "valid_until",
    )
    list_filter = ("sensor__client", "city", "department")
    search_fields = (
        "sensor__external_sensor_id",
        "sensor__sensor_name",
        "zone__name",
        "city",
        "department",
    )
    autocomplete_fields = ("sensor", "zone", "created_by")
    readonly_fields = ("created_at",)

    @admin.display(description="Finca / Invernadero")
    def facility_name(self, obj: SensorPlacement) -> str:
        facility = obj.farm_or_greenhouse
        return facility.name if facility else "—"
