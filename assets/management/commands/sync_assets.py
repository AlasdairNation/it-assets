import logging
import re

from django.core.management.base import BaseCommand
from django.utils.timezone import now

from assets.utils import ms_graph_get_servers, tenable_get_servers
from assets.models import Asset, AssetOwner

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

# Sync notes:
# - Defender & Tenable OS Names have different formatting and LOD, so they can refer to the same item but are registered as diff results. Should address this somehow in the future.
# - In the future it might be better to exclusively get data from tenable.
# - For the proper version, it'd be best to have a lot of these functions stored in a separate .py file just like ascender.py.
# - only tenable retrieves custodians right now, if we keep going with defender it's a good idea to retrieve custodians through that too.
def sync_servers():
    _sync_defender_servers()
    _sync_tenable_servers()

def _sync_defender_servers():
    # Retrieve servers from Defender
    ms_servers = ms_graph_get_servers()
    for s in ms_servers:
        if "dbca-" not in s['DeviceName']:
            asset, created = alias_get_or_create([s['DeviceName']])
            asset.os = s['OSDistribution']
            asset.os_version = s['OSVersion']
            if created:
                asset.aliases = [s['DeviceName']]
            asset.last_seen = now()
            asset.asset_defender_data=s
            asset.save()

        
def _sync_tenable_servers():
    # Retrieve all servers
    servers_of_custodians = tenable_get_servers()
    for servers in servers_of_custodians:
        owner, created = AssetOwner.objects.get_or_create(name=servers['custodian'])
        servers = servers['data']
        for s in servers:
            # Find all possible names used to identify the server
            aliases = []
            if len(s['hostname'])>0:
                aliases.append(s['hostname'][0].split(".")[0]) 
            if len(s['agent_name'])>0:
                aliases.append(s['agent_name'][0].split(".")[0])   
            if len(s['fqdn'])>0:
                aliases.append(s['fqdn'][0].split(".")[0])

            if len(aliases)>0:
                asset, created = alias_get_or_create(aliases)
                os, version = lint_tenable_os(s.get('operating_system',[''])[0])
                asset.owner = owner
                asset.aliases = list(set(aliases)) # removes duplicate aliases. Realistically should just rewrite this to use a set from the start
                if os:
                    asset.os = os
                if version:
                    asset.os_version = version
                if not created:
                    asset.last_seen = now()
                    asset.name = aliases[0]

                asset.asset_tenable_data=s
                asset.save()

# Get or Create doesn't really work for lists, so this is just a replacement
def alias_get_or_create(aliases):
    for name in aliases:
        if Asset.objects.filter(aliases__contains=name).exists():
            return Asset.objects.get(aliases__contains=name), False
    return Asset.objects.create(name=aliases[0], asset_type='S', last_seen=now()), True

# Tenable combines OS & Version number, so this is the only real way to extract that data.
# Right now it only extracts the first OS, so if a server has multiple it ignores it.
# For our sysstems, the second is typically a linux kernel if relevant.
def lint_tenable_os(os_string):
    os, version = [None, None]
    version_regex = r"\d+\.\d+(?:\.\d+)?" # Looks for Major.Minor or Major.Minor.Patch
    if "Debian" in os_string:
        version_regex = r"\d{1,2}" # Looks only for Major
    match = re.search(version_regex,os_string)
    if match: 
        os = re.split(version_regex, os_string)[0].strip()
        version = match.group().strip()
    elif "Build" in os_string:
        os = os_string.split("Build")[0]
    elif os_string is not None or "":
        os = os_string
    return os, version