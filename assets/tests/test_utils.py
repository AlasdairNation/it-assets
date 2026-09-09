from django.http import HttpResponse
from django.test import TestCase

from assets.utils import tenable_list_assets, retrieve_each_custodians_servers

class UtilsTestCase(TestCase):
    def test_tenable(self):
        assets = retrieve_each_custodians_servers()
        
        for asset in assets:
            if len(asset['operating_system'])>0 and len(asset['hostname'])>0 and not "dbca-" in asset['hostname'][0]:
                print(f"{asset['hostname'][0]} - {asset['operating_system'][0]}")