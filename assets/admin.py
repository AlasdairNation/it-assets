import json

from django.contrib import admin
from django.utils.html import mark_safe
from django.utils.translation import gettext_lazy as _

from .models import Asset, AssetOwner

@admin.register(AssetOwner)
class AssetOwnerAdmin(admin.ModelAdmin):
    search_fields = ["name"]

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    # Filter to find the source of the data
    # Might be better to migrate to a simple boolean field for both tenable and defender in the future instead of this
    class DataSourceFilter(admin.SimpleListFilter):
        """
        """

        title = _("Source")
        parameter_name = "asset_tenable_data"

        def lookups(self, request, model_admin):
            filter_list = [
                ("source_tenable", _("Only Tenable")),
                ("source_defender", _("Only Defender")),
                ("source_both", _("Both")),
                ("source_neither", _("Neither")),
            ]

            return filter_list

        def queryset(self, request, queryset):
            match self.value():
                case "source_tenable":
                    return queryset.filter(asset_defender_data__exact={}).exclude(asset_tenable_data__exact={})
                case "source_defender":
                    return queryset.filter(asset_tenable_data__exact={}).exclude(asset_defender_data__exact={})
                case "source_both":
                    return queryset.exclude(asset_tenable_data__exact={}).exclude(asset_defender_data__exact={})
                case "source_neither":
                    return queryset.filter(asset_defender_data__exact={}).filter(asset_tenable_data__exact={})
            
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
        "owner__name",
        "contacts__email",
        "systems__name",
        "os",
        "os_version"
    )

    list_filter = (
        DataSourceFilter,
        "owner",
        "asset_type",
        "os"
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
        "first_seen",
        "last_seen",
        "last_modified",
        "asset_defender_data_pprint",
        "asset_tenable_data_pprint"
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
                    "asset_defender_data_pprint",
                    "asset_tenable_data_pprint",
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

    def pprint_json(self, data=None):
        result = ""
        if data:
            result = json.dumps(data, indent=4, sort_keys=True)
            result = f"<pre>{result}</pre>"
            result =  mark_safe(result)
        return result

    def asset_defender_data_pprint(self, obj=None):
        if obj and obj.asset_defender_data:
            return self.pprint_json(data=obj.asset_defender_data)

    def asset_tenable_data_pprint(self, obj=None):
        if obj and obj.asset_tenable_data:
            return self.pprint_json(data=obj.asset_tenable_data)
        
    asset_defender_data_pprint.short_description = "Defender Data"
    asset_tenable_data_pprint.short_description = "Tenable Data"