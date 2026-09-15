from django.contrib import admin

from .models import (
    AgronomicRelationshipAlert,
    AgronomicVariableRelationship,
    SensorAutomationPolicy,
)


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


@admin.register(AgronomicVariableRelationship)
class AgronomicVariableRelationshipAdmin(admin.ModelAdmin):
    list_display = (
        "client",
        "crop_name",
        "sensor_name",
        "name",
        "relationship_type",
        "is_enabled",
        "updated_at",
    )
    list_filter = ("client", "relationship_type", "is_enabled")
    search_fields = (
        "crop_name",
        "sensor_id",
        "sensor_name",
        "name",
        "agronomic_goal",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(AgronomicRelationshipAlert)
class AgronomicRelationshipAlertAdmin(admin.ModelAdmin):
    list_display = (
        "client",
        "relationship",
        "name",
        "logic",
        "severity",
        "duration_minutes",
        "is_enabled",
        "updated_at",
    )
    list_filter = ("client", "logic", "severity", "is_enabled")
    search_fields = (
        "name",
        "relationship__name",
        "variable_a_key",
        "variable_b_key",
        "email_recipients",
        "whatsapp_recipients",
    )
    readonly_fields = ("created_at", "updated_at")
