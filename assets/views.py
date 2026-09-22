from django.views.generic import View
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control
from django.conf import settings
from django.http import JsonResponse

from .models import Asset


class AssetAPIResource(View):
    """An API view that returns JSON of assets."""

    @method_decorator(cache_control(max_age=settings.API_RESPONSE_CACHE_SECONDS, private=True))
    def get(self, request, *args, **kwargs):
        queryset = (
            Asset.objects.all()
            .select_related(
                "owner",
            )
            .order_by("name")
        )

        # Queryset filtering.
        if "pk" in kwargs and kwargs["pk"]:  # Allow filtering by object PK.
            queryset = queryset.filter(pk=kwargs["pk"])
        if "name" in self.request.GET:  # Allow basic filtering on name.
            queryset = queryset.filter(name__icontains=self.request.GET["name"])
        if "owner" in self.request.GET:  # Allow basic filtering on owner.
            queryset = queryset.filter(owner__name=self.request.GET["owner"])
        if "os" in self.request.GET:  # Allow basic filtering on os.
            queryset = queryset.filter(os__icontains=self.request.GET["os"])

        assets = [
            {
                "id": asset.pk,
                "name": asset.name,
                "aliases": asset.aliases,
                "description": asset.description,
                "contacts": asset.asset_contacts,
                "systems": asset.associated_systems,
                "os": asset.os,
                "os_version": asset.os_version,
                "defender_data": asset.defender_data,
                "tenable_data": asset.tenable_data,
                "tags": asset.display_tags
            }
            for asset in queryset
        ]

        return JsonResponse(assets, safe=False)