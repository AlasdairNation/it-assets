from assets.models import Asset
from organisation.models import DepartmentUser
from itsystems.models import ITSystemRecord

from django.test import TestCase

from mixer.backend.django import mixer

class AssetModelTestCase(TestCase):

    def setUp(self):
        pass

    def test_add_tag(self):
        pass

    def test_remove_tag(self):
        pass

    def test_has_tag(self):
        pass

    def test_split_tenable_os_and_version(self):
        pass

    def test_os_version_regex_validation(self):
        pass

class AssetTagTestCase(TestCase):
    def test_enforced_uniqueness(self):
        pass


class RandomAssetGenerator():
    tenable_id_inc = 0

    def __create(self):
        self.tenable_id_inc += 1
        return mixer.blend(
            Asset,
            tenable_id = self.tenable_id_inc,
            name = mixer.RANDOM,
            os = mixer.RANDOM("Windows", "Linux", "MaxOS", "Other"),
            os_version = mixer.RANDOM,
            description = mixer.RANDOM("16","24.04","10.1.8","0.0.1"),
            contacts = mixer.blend(DepartmentUser),
            systems = mixer.blend(ITSystemRecord),
        )
    
    def generate(self,generations: int):
        return tuple([self.__create() for i in range(3)])