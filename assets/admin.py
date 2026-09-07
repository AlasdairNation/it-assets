from django.contrib import admin

from .models import Asset, AssetOwner

@admin.register(AssetOwner)
class AssetOwnerAdmin(admin.ModelAdmin):
    search_fields = ["name"]

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    ordering = ["name"]
    list_display = (
        "name",
        "asset_type",
        "owner",
        "os",
        "os_version",
        "asset_contacts",
        "associated_systems"
    )
    search_fields = (
        "name",
        "asset_type",
        "description",
        "owner",
        "contacts",
        "systems",
        "os",
        "os_version"
    )

    list_filter = (
        "asset_type",
        "os",
        "owner"
    )

    autocomplete_fields = (
        "contacts",
        "systems"
    )

    readonly_fields = (
        "name",
        "asset_type",
        "os",
        "os_version",
        "asset_type_data",
        "first_seen",
        "last_seen",
        "last_modified"
    )

    fieldsets = (
        (
            "Overview",
            {
                "fields":(
                    "name",
                    "asset_type",
                    "description"
                ),
            },
        ),
        (
            "Associations",
            {
                "fields":(
                    "owner",
                    "contacts",
                    "systems"
                ),
            },
        ),
        (
            "Technical Info",
            {
                "fields":(
                    "os",
                    "os_version",
                    "asset_type_data"
                ),
            },
        ),
        (
            "Meta-Data",
            {
                "fields":(
                    "first_seen",
                    "last_seen",
                    "last_modified"
                ),
            },
        ),
    )