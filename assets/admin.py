import json

from django.contrib import admin
from django.utils.html import mark_safe
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import Asset, AssetTagCategory, AssetTag

class AssetTagInline(admin.TabularInline):
    model = AssetTag
    extra = 0
    readonly_fields = ("total_assets",)
    fields = ("name", "total_assets")

    @admin.display(description="Total Tagged Assets")
    def total_assets(self, obj):
        """
        Provides a count of all assets with this tag, and includes a hyperlink to the pre-filtered admin asset page for this tag.
        """
        num_assets = obj.number_of_tagged_assets()
        url = reverse("service_desk_admin:assets_asset_changelist", query={f"{obj.category.name.lower()}_tag":obj.pk})
        return mark_safe(f"<a href='{url}'>{num_assets}</a>")
        

@admin.register(AssetTagCategory)
class AssetTagCategoryAdmin(admin.ModelAdmin):
    """
    Provides an admin interface for users to review tags and minor tag statistics.
    Uses an inline asset tag field to allow for a heirarchical structure.
    """
    search_fields = ("name",) 
    readonly_fields = ("total_tags","total_tagged_assets")
    list_display = ("category","total_tags","total_tagged_assets")
    inlines = [AssetTagInline,]

    readonly_fields = ("total_tags",)
    fields = ("name", "total_tags")

    @admin.display(description="Category")
    def category(self,obj):
        return obj.name

    @admin.display(description="Total Tags")
    def total_tags(self,obj):
        """
        Provides a count of all tag values for this tag category.
        """
        return obj.number_of_values()

    
    @admin.display(description="Total Tagged Assets")
    def total_tagged_assets(self,obj):
        """
        Provides a count of all assets tagged with this category, and provides a link to a pre-filtered admin asset page for this tag category.
        """
        assets = []
        total_assets = sum(set([len(x.tagged_assets.all()) for x in obj.tag_values.all()]))
        url = reverse("service_desk_admin:assets_asset_changelist", query={f"tags__category__id__exact":obj.pk})
        return mark_safe(f"<a href='{url}'>{total_assets}</a>")

@admin.register(AssetTag)
class AssetTagAdmin(admin.ModelAdmin):
    """
    Registers the tag model with django admin so it can be used in autocomplete fields, but hides it from users.
    """
    def get_model_perms(self, request): 
        return {}
    search_fields = ("tag_id",)

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
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

    def get_list_filter(self, request):
        """
        Dynamically creates filter classes from tags found in the db.
        Allows new tag categories to be created without the need to manually maintain the filters.
        """
        self.list_filter = self.list_filter_base + tuple([
            type(
                f"{cat.name}Filter",
                (self.TagFilterTemplate, ), 
                {"title":f"Tag: {cat.name}","parameter_name":f"{cat.name.lower()}_tag","category":cat.name}
            ) 
            for cat in AssetTagCategory.objects.all().order_by("name")
        ])

        return super().get_list_filter(request)

    # Base filters - Dynamic tag filters are appended to this
    list_filter_base = ("os", "tags__category")

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