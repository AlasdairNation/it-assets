import json

from django.contrib import admin
from django.utils.html import mark_safe
from django.utils.translation import gettext_lazy as _

from .models import Asset, AssetTagCategory, AssetTag

class TagFilterTemplate(admin.SimpleListFilter):
    """
    A custom tag filter template class to allow for filtering on categorized tags.
    Child classes must provide a class string variable for title, parameter_name, and category.
    """

    def lookups(self, request, model_admin):
        filter_list = []

        tag_category, _c = AssetTagCategory.objects.get_or_create(name=self.category)
        location_tags = AssetTag.objects.filter(category=tag_category).order_by("name")
        for tag in location_tags:
            filter_list.append((tag.pk, _(tag.name)))


        return filter_list

    def queryset(self, request, queryset):
        if self.value() is not None:
            return queryset.filter(tags__id__exact=self.value())

@admin.register(AssetTag)
class AssetTagAdmin(admin.ModelAdmin):
    search_fields = ("name", "tag_id",)
    list_display = (
        "name",
        "category",
    )
    list_filter = (
        "category",
    )

@admin.register(AssetTagCategory)
class AssetTagCategoryAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_display = ("name",)

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    class DataSourceFilter(admin.SimpleListFilter):
        """
        A custom filter that determines which source imported data came from.
        """

        title = _("Source")
        parameter_name = "data_source"

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
                    return queryset.filter(defender_data__exact={}).exclude(tenable_data__exact={})
                case "source_defender":
                    return queryset.filter(tenable_data__exact={}).exclude(defender_data__exact={})
                case "source_both":
                    return queryset.exclude(tenable_data__exact={}).exclude(defender_data__exact={})
                case "source_neither":
                    return queryset.filter(defender_data__exact={}).filter(tenable_data__exact={})
                
    class ContainedTagsFilter(admin.SimpleListFilter):
        """
        A custom filter that allows users to filter by the category of tags present in an asset.
        """

        title = _("Contained Tag")
        parameter_name = "contains_tag"

        def lookups(self, request, model_admin):
            filter_list = []

            location_tags = AssetTagCategory.objects.all().order_by("name")
            for tag in location_tags:
                filter_list.append((tag.pk, _(tag.name)))

            return filter_list

        def queryset(self, request, queryset):
            if self.value() is not None:
                return queryset.filter(tags__category__id__exact=self.value())

    # Filters for each of the tag categories
    # Dynamically creates filter classes for each tag.
    tag_filters = tuple([
        type(
            f"{cat.name}Filter",
            (TagFilterTemplate, ), 
            {"title":f"Tag: {cat.name}","parameter_name":f"{cat.name.lower()}_tag","category":cat.name}
        ) 
        for cat in AssetTagCategory.objects.all()
    ])

    list_filter = (
        "os",
        DataSourceFilter,
        ContainedTagsFilter,
    ) + tag_filters


    ordering = ["name"]
    list_display = (
        "name",
        "custodian",
        "asset_type",
        "os",
        "os_version",
        "asset_contacts",
        "associated_systems",
        "display_tags"
    )
    
    search_fields = (
        "name",
        "description",
        "contacts__email",
        "systems__name",
        "tags__name",
        "os",
        "os_version"
    )

    autocomplete_fields = (
        "contacts",
        "systems",
        "tags",
    )

    readonly_fields = (
        "name",
        "asset_type",
        "custodian",
        "os",
        "os_version",
        "first_seen",
        "last_seen",
        "last_modified",
        "defender_data_pprint",
        "tenable_data_pprint",
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
                    "custodian",
                    "contacts",
                    "systems",
                    "tags",
                ),
            },
        ),
        (
            "Technical Info",
            {
                "fields":(
                    "os",
                    "os_version",
                    "defender_data_pprint",
                    "tenable_data_pprint",
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

    def defender_data_pprint(self, obj=None):
        if obj and obj.defender_data:
            return self.pprint_json(data=obj.defender_data)

    def tenable_data_pprint(self, obj=None):
        if obj and obj.tenable_data:
            return self.pprint_json(data=obj.tenable_data)
        
    defender_data_pprint.short_description = "Defender Data"
    tenable_data_pprint.short_description = "Tenable Data"