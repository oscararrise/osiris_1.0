from django.contrib import admin

from .models import (
    Client,
    ClientDataSource,
    ClientMembership,
    ClientModule,
    ControlEvent,
    PlatformModule,
    SupportRequest,
)


class ClientDataSourceInline(admin.StackedInline):
    model = ClientDataSource
    extra = 0
    max_num = 1
    fieldsets = (
        (None, {"fields": ("name", "adapter_key", "database_alias", "is_active")}),
        ("Adaptador", {"fields": ("settings",), "classes": ("collapse",)}),
    )


class ClientModuleInline(admin.TabularInline):
    model = ClientModule
    extra = 0
    autocomplete_fields = ("module",)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = (ClientDataSourceInline, ClientModuleInline)


@admin.register(ClientMembership)
class ClientMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "client", "access_level", "is_active")
    list_filter = ("client", "access_level", "is_active")
    search_fields = ("user__username", "user__email", "client__name")
    autocomplete_fields = ("user", "client")


@admin.register(PlatformModule)
class PlatformModuleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "category", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "code", "description")


@admin.register(ClientDataSource)
class ClientDataSourceAdmin(admin.ModelAdmin):
    list_display = ("client", "name", "adapter_key", "database_alias", "is_active")
    list_filter = ("adapter_key", "is_active")
    search_fields = ("client__name", "database_alias")


@admin.register(ClientModule)
class ClientModuleAdmin(admin.ModelAdmin):
    list_display = ("client", "module", "is_enabled", "minimum_access_level")
    list_filter = ("client", "is_enabled", "minimum_access_level")
    autocomplete_fields = ("client", "module")


@admin.register(ControlEvent)
class ControlEventAdmin(admin.ModelAdmin):
    list_display = ("client", "created_by", "created_at")
    list_filter = ("client", "created_at")
    search_fields = ("client__name", "created_by__username")
    readonly_fields = ("client", "created_by", "payload", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(SupportRequest)
class SupportRequestAdmin(admin.ModelAdmin):
    list_display = ("request_type", "client", "created_by", "status", "created_at")
    list_filter = ("status", "client", "created_at")
    search_fields = ("description", "client__name", "created_by__username")
    readonly_fields = ("client", "created_by", "request_type", "description", "created_at")
    list_editable = ("status",)

    def has_add_permission(self, request):
        return False
