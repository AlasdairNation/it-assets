from django.urls import reverse
from mixer.backend.django import mixer

import json

from itassets.test_api import ApiTestCase
from .test_model import create_random_record
from itsystems.models import ITSystemRecord


class ITSystemRecordAPIResourceTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        create_random_record().save()
        create_random_record().save()
        create_random_record().save()


    def test_list(self):
        """Test the ITSystemRecordAPIResource list responses"""

        records = ITSystemRecord.objects.all()

        url = reverse("it_system_api_resource")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Response should contain each of the records, and should match the size of the database
        for record in records:
            self.assertContains(response, record.system_id)
        content = json.loads(response.content)
        self.assertEqual(len(content), 3)

    def test_search(self):
        pass