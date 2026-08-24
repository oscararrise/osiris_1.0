from django.contrib import admin

from .models import SensorAutomationPolicy


@admin.register(SensorAutomationPolicy)
class SensorAutomationPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "client",
        "sensor_name",
        "automation_level",
        "is_enabled",
        "requires_confirmation",
        "email_enabled",
        "whatsapp_enabled",
        "updated_at",
    )
    list_filter = (
        "client",
        "automation_level",
        "is_enabled",
        "requires_confirmation",
        "email_enabled",
        "whatsapp_enabled",
    )
    search_fields = ("sensor_id", "sensor_name", "metric_name", "email_recipients")
    readonly_fields = ("created_at", "updated_at")
