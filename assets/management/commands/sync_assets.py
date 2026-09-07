import logging

from django.core.management.base import BaseCommand

from assets.asset_syncing import sync_servers


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
