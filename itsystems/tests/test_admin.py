from django.contrib.auth import get_user_model
from django.urls import reverse
from mixer.backend.django import mixer

from itsystems.models import ITSystemRecord
from itassets.test_api import ApiTestCase

User = get_user_model()


class ITSystemRecordAdminTestCase(ApiTestCase):
    def setUp(self):
        super(ITSystemRecordAdminTestCase, self).setUp()
        # Create & log in an admin user.
        self.admin_user = mixer.blend(User, username="admin", is_superuser=True, is_staff=True)
        self.admin_user.set_password("pass")
        self.admin_user.save()
        self.client.login(username="admin", password="pass")
        mixer.cycle(5).blend(ITSystemRecord)

    def test_itsystemrecord_export(self):
        """Test the customised ITSystemRecordExport admin view"""
        url = reverse("admin:itsystems_itsystemrecord_export")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.has_header("Content-Disposition"))
        self.assertEqual(response["Content-Type"], "text/csv")

    def test_itsystemrecord_import(self):
        """Test the customised ITSystemRecordImport admin view"""
        url = reverse("admin:itsystems_itsystemrecord_import")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
