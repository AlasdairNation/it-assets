import logging
import requests
import json
import os
import time

from django.conf import settings

LOGGER = logging.getLogger("assets")

def get_tenable_key_string():
    # Manual right now, but could be retrieved dynamically from azure key vault
    return f"accessKey={os.environ["TENABLE_ACCESS_KEY"]};secretKey={os.environ["TENABLE_SECRET_KEY"]}"

def tenable_list_assets():
    """
    Queries the Tenable Rest endpoint to retrieve all registered assets, returned as a dict of the json content.
    """
    headers = {
        "Content-Type": "application/json",
        "X-APIKeys": get_tenable_key_string()
    }
    url = "https://cloud.tenable.com/assets/"
    resp = requests.get(url,headers=headers)
    resp.raise_for_status()

    return json.loads(resp.content)

def tenable_get_servers():
    """
    Retrieves all tagged servers from the tenable api and their custodian. Returned as a list of tuples [<list<dict>: servers>, <string: custodian>]
    """
    custodians = ["OIM", "BCS","BGPA","Fleet","FMB","FSB","GIS","PVS","RFMS","RIA","ZPA"]
    assets = []
    headers = {
        "Content-Type": "application/json",
        "X-APIKeys": get_tenable_key_string()
    }

    for custodian in custodians:
        url = f"https://cloud.tenable.com/workbenches/assets?filter.0.filter=tag.Custodian&filter.0.quality=eq&filter.0.value={cust}"
        resp = requests.get(url,headers=headers)
        resp.raise_for_status()
        assets.append((json.loads(resp.content)['assets'],custodian))

    return assets

def tenable_export_assets() -> list:
    """
    Initiates a Tenable asset export and downloads the result once the export is complete.
    """
    assets = []
    export_uuid = None
    chunks_available = []

    # Initiate asset export
    try:
        export_uuid = __tenable_initiate_export(automatic_retries=3)
        LOGGER.info("Initiated Tenable asset export")
    except (requests.exceptions.HTTPError, requests.exceptions.RequestException) as exc:
        LOGGER.warning("Failed to initiate Tenable asset export", exc_info=exc)

    # Checks export status until the export is completed, failed, or the check limit as run out.
    if export_uuid:
        LOGGER.info("Waiting for export to complete...")
        times_checked = 0
        while times_checked < settings.TENABLE_EXPORT_STATUS_CHECK_LIMIT:
            try:
                # Attempt status check
                times_checked += 1
                response = __tenable_check_export_status(export_uuid=export_uuid, automatic_retries=3)
                # Retrieve status
                status = response.get("status") if response else None
                # Sleeps if export is still in process, else reports the result and exits the loop
                match status:
                    case "QUEUED" | "PROCESSING": # Export still in process - Wait for <TENABLE_EXPORT_CHECK_DELAY> seconds
                        LOGGER.info(f"Tenable export still in process - Sleeping for {settings.TENABLE_EXPORT_CHECK_DELAY} seconds...")
                        time.sleep(settings.TENABLE_EXPORT_CHECK_DELAY)
                    case "FINISHED": # Export finished 
                        chunks_available = response.get("chunks_available",[])
                        LOGGER.info(f"Tenable export complete - {len(chunks_available)} chunks available for download")
                        break
                    case "ERROR": # Tenable ran into an error while exporting the assets
                        LOGGER.warning(f"Failed to export Tenable assets -  ERROR: {response.get("reason", "Unknown Error, response did not contain error message")}")
                        break
                    case "CANCELLED": # Export was cancelled by admin - Likely rare to happen, but worth accounting for
                        LOGGER.warning("Failed to export Tenable assets - request cancelled by an administrator")
                        break
                    case _: # initiate asset export returned empty
                        LOGGER.warning("Failed to export Tenable assets - Empty return value from status check")
                        break
            except requests.exceptions.HTTPError as exc:
                LOGGER.warning(f"Failed to export Tenable assets - {exc.response.status_code} Error raised during status check", exc_info=exc)
                break    

    # Downloads asset export
    chunks_downloaded = 0
    if len(chunks_available)>0:
        LOGGER.info("Downloading chunks...")
        for chunk_id in chunks_available:
            try:
                chunk = __tenable_download_export_chunk(export_uuid=export_uuid, chunk_id=int(chunk_id), automatic_retries=3)
                if chunk:
                    assets.extend(chunk)
                    chunks_downloaded += 1
                    LOGGER.info(f"Downloaded chunk {chunk_id}")
                else:
                    LOGGER.info(f"Failed to download chunk {chunk_id} - No data returned")
            except requests.exceptions.HTTPError as exc:
                LOGGER.warning(f"Failed to download chunk {chunk_id} - {exc.response.status_code} Error raised during status check", exc_info=exc)

        LOGGER.info(f"""Download complete: Chunks downloaded - {chunks_downloaded}/{len(chunks_available)} | Assets downloaded - {len(assets)}""")

    return assets




def __tenable_initiate_export(automatic_retries: int = 0) -> str | None:
    """
    Queries the Tenable Nessus endpoint to initate an export of all recorded assets, and returns the export uuid.
    If an automatic_retries number is specified, any 429 errors will automatically retry that many times.
    """
    url = "https://cloud.tenable.com/assets/v2/export"

    payload = {
        "include_resource_tags": True,
        "include_open_ports": False,
        "chunk_size": 1000
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "X-ApiKeys": get_tenable_key_string()
    }

    response = requests.post(url, json=json.dumps(payload), headers=headers)

    # Automatically sleep and retry any rate 429 rate limiting responses
    if response.status_code == '429' and automatic_retries > 0:
        attempts = 0
        while response.status_code == '429' and automatic_retries > attempts:
            attempts += 1
            time.sleep(int(response.headers['retry-after']))
            response = requests.post(url, json=payload, headers=headers)

    response.raise_for_status()
    return json.loads(response.content).get('export_uuid')

def __tenable_check_export_status(export_uuid: str, automatic_retries: int = 0) -> dict | None:
    """
    Queries the Tenable Nessus endpoint to check the status of a given asset export job. 
    Returns a tuple (bool, list[int]) of the completion status and list of available chunks if the export uuid is valid, else returns None.
    If an automatic_retries number is specified, any 429 errors will automatically retry that many times.
    """

    url = f"https://cloud.tenable.com/assets/export/{export_uuid}/status"

    headers = {
        "accept": "application/json",
        "X-ApiKeys": get_tenable_key_string()
    }

    response = requests.get(url, headers=headers)

    # Automatically sleep and retry any rate 429 rate limiting responses
    if response.status_code == '429' and automatic_retries > 0:
        attempts = 0
        while response.status_code == '429' and automatic_retries > attempts:
            attempts += 1
            time.sleep(int(response.headers['retry-after']))
            response = requests.get(url, headers=headers)

    response.raise_for_status()

    content = json.loads(response.content)

    return content

def __tenable_download_export_chunk(export_uuid: str, chunk_id: int, automatic_retries: int = 0) -> list | None:
    """
    Queries the Tenable Nessus endpoint to retrieve a chunk of the asset export. 
    Returns a list of dicts representing the assets.
    If an automatic_retries number is specified, any 429 errors will automatically retry that many times.
    """
    url = f"https://cloud.tenable.com/assets/export/{export_uuid}/chunks/{chunk_id}"

    headers = {
        "accept": "application/json",
        "X-ApiKeys": get_tenable_key_string()
    }

    response = requests.get(url, headers=headers)

    # Automatically sleep and retry any rate 429 rate limiting responses
    if response.status_code == '429' and automatic_retries > 0:
        attempts = 0
        while response.status_code == '429' and automatic_retries > attempts:
            attempts += 1
            time.sleep(int(response.headers['retry-after']))
            response = requests.get(url, headers=headers)

    response.raise_for_status()

    return json.loads(response.content)