import requests
import json
import os
from typing import Dict, List, Optional

from msal import ConfidentialClientApplication

def advanced_hunting_client_token() -> Dict | None:
    """Uses the Microsoft msal library to obtain an access token for the Graph API.
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

def ms_graph_query_advanced_hunting(query: str, token: Optional[Dict] = None) -> List | None:
    """
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