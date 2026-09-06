from django.contrib import admin

from .models import SatelliteField, SatelliteJob, SatelliteMeasurement, SatelliteScene


@admin.register(SatelliteField)
class SatelliteFieldAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "crop_type", "area_ha", "is_active", "last_sync_at")
    list_filter = ("client", "is_active", "crop_type")
    search_fields = ("name", "client__name", "crop_type", "eosda_field_id")
    readonly_fields = ("created_at", "updated_at", "last_sync_at")


@admin.register(SatelliteScene)
class SatelliteSceneAdmin(admin.ModelAdmin):
    list_display = ("field", "dataset", "captured_at", "cloud_cover", "provider")
    list_filter = ("provider", "dataset", "field__client")
    search_fields = ("field__name", "field__client__name", "view_id")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("field",)


@admin.register(SatelliteMeasurement)
class SatelliteMeasurementAdmin(admin.ModelAdmin):
    list_display = ("scene", "index_name", "average", "minimum", "maximum")
    list_filter = ("index_name", "scene__field__client")
    search_fields = ("scene__field__name", "scene__view_id", "index_name")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("scene",)


@admin.register(SatelliteJob)
class SatelliteJobAdmin(admin.ModelAdmin):
    list_display = ("field", "job_type", "status", "attempts", "next_check_at", "created_at")
    list_filter = ("job_type", "status", "field__client")
    search_fields = ("field__name", "field__client__name", "provider_task_id")
    readonly_fields = ("created_at", "updated_at", "started_at", "finished_at")
    autocomplete_fields = ("field", "scene")
