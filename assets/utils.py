import requests
import json
import os

from typing import Dict, List, Optional

from msal import ConfidentialClientApplication

from django.utils.timezone import now

from assets.models import Asset

def advanced_hunting_client_token() -> Dict | None:
    """Uses the Microsoft msal library to obtain an access token for the Graph API.
    Retrieves a token that allows for Defender advanced hunting queries.
    Ref: https://docs.microsoft.com/en-us/python/api/msal/msal.application.confidentialclientapplication
    """
    azure_tenant_id = os.environ["AZURE_TENANT_ID"]
    client_id = os.environ["ADVANCED_HUNTING_CLIENT_ID"]
    client_secret = os.environ["ADVANCED_HUNTING_CLIENT_SECRET"]
    context = ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{azure_tenant_id}",
    )
    token = context.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

    return token

def get_tenable_key_string():
    # Manual right now, but could be retrieved dynamically from azure key vault
    return f"accessKey={os.environ["TENABLE_ACCESS_KEY"]};secretKey={os.environ["TENABLE_SECRET_KEY"]}"

def ms_graph_query_advanced_hunting(query: str, token: Optional[Dict] = None) -> List | None:
    """
    Queries the advanced hunting endpoint for a given query and returns the results as an array of dicts.
    """
    if not token:
        token = advanced_hunting_client_token()
    if not token:  # The call to the MS API occasionally fails and returns None.
        return None
    headers = {
        "Authorization": f"Bearer {token['access_token']}",
        "Content-Type": "application/json",
    }
    url = "https://graph.microsoft.com/v1.0/security/runHuntingQuery"
    #resp = requests.post(url, headers=headers, json=json.dumps(query))
    resp = requests.post(url,headers=headers, json={"query": query})
    resp.raise_for_status()

    return json.loads(resp.content)['results']

def ms_graph_get_servers(token: Optional[Dict] = None):
    # Query is manual for prototype, but might be better to have it ported in through a config file
    query = r"""
    DeviceInfo
    | where OSPlatform has ("Linux")
        or OSPlatform startswith "WindowsServer"
    | where DeviceType == @"Server"
    | summarize arg_max(TimeGenerated, *) by DeviceId
    | extend ResourceGroup = extract(@"resourceGroups\/([^\/]+)", 1, AzureResourceId)
    | project
        DeviceName = tostring(split(DeviceName,".")[0]),
        DeviceType = strcat_array(parsejson(DeviceManualTags), ","),
        OSPlatform,
        OSDistribution,
        OSVersion,
        OSBuild,
        ExposureLevel,
        CloudPlat = strcat_array(parsejson(CloudPlatforms), ","),
        MachineGroup,
        OnboardingStatus,
        AzureVmSubscriptionId,
        ResourceGroup,
        TimeGenerated
    | order by DeviceName asc
    """
    return ms_graph_query_advanced_hunting(query=query, token=token)

def alias_get_or_create(aliases: list, asset_type: str):
    """
    Get or Create an asset based on the list of aliases for that asset.
    Returns a tuple of (Asset <Asset>, Created <bool>).
    """
    for name in aliases:
        if Asset.objects.filter(aliases__contains=name).exists():
            return Asset.objects.get(aliases__contains=name), False
    return Asset.objects.create(name=aliases[0], asset_type=asset_type, last_seen=now()), True