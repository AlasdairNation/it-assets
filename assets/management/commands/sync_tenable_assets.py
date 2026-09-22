import logging

from django.core.management.base import BaseCommand

from assets.tenable_requests import tenable_export_assets

from assets.models import Asset

class Command(BaseCommand):
    help = "Synchronises department assets with Tenable assets"

    def handle(self, *args, **options):
        """
        Retrieves all Tenable assets and uses that to create / update assets.
        """
        logger = logging.getLogger("assets")
        try:
            assets = tenable_export_assets()
            count = 0
            logger.info(f"Updating {len(assets)} department assets")
            for asset in assets:
                count += 1
                found_asset, created = Asset.objects.get_or_create(tenable_id=asset['id'])
                found_asset.update_from_tenable_data(asset)
                if created:
                    logger.info(f"Created asset {found_asset.pk} - {found_asset.name or ""}")
                else:
                    logger.info(f"Updated asset {found_asset.pk} - {found_asset.name or ""}")
            logger.info(f"Successfully updated {len(assets)} department assets")
            
        except Exception as exc:
            logger.warning("Failed to sync Tenable assets", exc_info=exc)