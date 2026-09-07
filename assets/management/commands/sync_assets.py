import logging

from django.core.management.base import BaseCommand
from django.utils.timezone import now

from assets.utils import ms_graph_get_servers
from assets.models import Asset

class Command(BaseCommand):
    help = "Checks the IT Systems Register for disabled / addressbook excluded accounts in contacts, and notifies the ITPnP Mailbox"

    def add_arguments(self, parser):
        parser.add_argument(
            "-e",
            "--send-email",
            action="store_true",
            dest="send_email",
            help="(Optional) Flag to send notification emails to ITPnP Mailbox (default behaviour is logging only)",
        )

    def handle(self, *args, **options):
        """
        Iterates throughout the IT Systems Register, flagging any user contact that doesn't appear on the addressbook, then sends an email to the ITPnP Mailbox to notify them of this issue.
        """
        sync_servers()

def sync_servers():
    # Retrieve servers from Defender
    servers = ms_graph_get_servers()
    for s in servers:
        asset, created = Asset.objects.get_or_create(
            name=s['DeviceName'], 
            defaults={'asset_type':'S', 'last_seen':now()})
        asset.os = s['OSDistribution']
        asset.os_version = s['OSVersion']
        asset.asset_type_data = s
        asset.last_seen = now()
        asset.save()
    