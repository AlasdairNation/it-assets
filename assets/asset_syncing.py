from assets.utils import ms_graph_get_servers
from assets.models import Asset

def sync_servers():
    # Retrieve servers from Defender
    servers = ms_graph_get_servers()
    for s in servers:
        asset, created = Asset.objects.get_or_create(
            name=s['DeviceName'], 
            defaults={'asset_type':'S'})
        asset.os = s['OSDistribution']
        asset.os_version = s['OSVersion']
        asset.asset_type_data = s
        asset.save()


