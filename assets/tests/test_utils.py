from django.http import HttpResponse
from django.test import TestCase

from assets.asset_syncing import sync_servers

class UtilsTestCase(TestCase):
    def test_ms_graph_get_servers(self):
        sync_servers()