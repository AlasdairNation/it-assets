from django.urls import reverse

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
        self.records = ITSystemRecord.objects.all()

    def test_list(self):
        """Test the ITSystemRecordAPIResource list responses"""
        url = reverse("it_system_api_resource")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content)
        # Response should contain each of the records, and should match the size of the database
        # Tests id, string and fk field
        for record in self.records:
            self.assertContains(response, record.system_id)
            self.assertContains(response, record.name)
            self.assertContains(response, record.division.name)
        content = json.loads(response.content)
        self.assertEqual(len(content), 3)

    def test_search(self):
        """Test the ITSystemRecordAPIResource search for record functionality"""

        url = reverse("it_system_api_resource", kwargs={"system_id": self.records[0].system_id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.records[0].system_id)
        self.assertNotContains(response, self.records[1].system_id)
        self.assertNotContains(response, self.records[2].system_id)

    def test_record_edit(self):
        """Test the ITSystemRecordAPIResource edit record functionality"""

        url = reverse("it_system_api_resource", kwargs={"system_id": self.records[0].system_id})
        old_name = self.records[0].name
        new_name = old_name[:-1] + "added_string"
        data = self.records[0].to_dict()
        data["name"] = new_name
        json_data = json.dumps({"force": False, "record": data})
        response = self.client.post(path=url, data=json_data, secure=False, content_type="application/json")
        updated_record = ITSystemRecord.objects.get(system_id=data["system_id"])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, new_name)
        self.assertEqual(updated_record.name, new_name)

    def test_contact_replace(self):
        """Test the ITSystemRecordAPIResource replace contact functionality"""

        target1 = self.records[0]
        target2 = self.records[1]
        non_target = self.records[2]

        target1.technology_custodian = target2.business_service_owner
        target1.information_custodian = target2.business_service_owner
        target1.save()

        old_contact = target2.business_service_owner.email
        new_contact = target1.business_service_owner.email

        url = reverse("it_system_api_resource")
        json_data = json.dumps({"new_contact": new_contact, "old_contact": old_contact})
        response = self.client.post(path=url, data=json_data, secure=False, content_type="application/json")

        # Ensures response is correct
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, target1.system_id)
        self.assertContains(response, target2.system_id)
        self.assertNotContains(response, non_target.system_id)
        self.assertContains(response, "business_service_owner")
        self.assertContains(response, "technology_custodian")
        self.assertContains(response, "information_custodian")
        self.assertNotContains(response, "system_owner")

        target1 = ITSystemRecord.objects.get(pk=target1.pk)
        target2 = ITSystemRecord.objects.get(pk=target2.pk)
        non_target = ITSystemRecord.objects.get(pk=non_target.pk)

        # Ensures that relevant information has been properly updated
        self.assertEqual(target1.technology_custodian.email, new_contact)
        self.assertEqual(target1.information_custodian.email, new_contact)
        self.assertEqual(target2.business_service_owner.email, new_contact)
