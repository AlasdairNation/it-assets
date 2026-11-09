import logging

from django.core.management.base import BaseCommand

from assets.tenable_requests import get_tenable_images


class Command(BaseCommand):
    help = ""

    logger = logging.getLogger("assets")

    def handle(self, *args, **options):
        """
        """
        result = get_tenable_images()
        print(result)
        
