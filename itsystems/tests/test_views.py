from django.urls import reverse

from itassets.test_api import ApiTestCase

class ViewsTestCase(ApiTestCase):
    def test_view_it_systems_register(self):
        """
        Test the it systems register view.
        Will be expanded upon after the register view is completed.
        """
        url = reverse("it_systems_register")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

