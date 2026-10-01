from assets.models import Asset
from organisation.models import DepartmentUser
from itsystems.models import ITSystemRecord

from django.test import TestCase

from mixer.backend.django import mixer

class AssetModelTestCase(TestCase):

    def setUp(self):
        self.asset1, self.asset2, self.asset3 = RandomAssetGenerator().generate(3)
        self.asset1.save()
        self.asset2.save()
        self.asset3.save()

    def test_add_tag(self):
        """
        validates that the add_tag function works as intended
        """

        # Basic Add
        self.asset1.add_tag("test_tag_1","test_category")
        self.asset1.add_tag("test_tag_2","test_category_2")
        self.asset1.save()
        self.assertEqual(len(self.asset1.tags.all()),2)
        self.assertIn("test_tag_1",self.asset1.display_tags)
        self.assertIn("test_tag_2",self.asset1.display_tags)

        # Add tag with new value but existing category
        self.asset2.add_tag("new_tag_test","test_category")
        self.asset2.save()
        self.assertEqual(len(self.asset2.tags.all()),1)
        self.assertIn("new_tag_test",self.asset2.display_tags)
        self.assertIn("test_category",self.asset2.display_tags)

        # Add tag with existing value but new category
        self.asset3.add_tag("test_tag_1","diff_category")
        self.asset1.add_tag("test_tag_1","diff_category")
        self.asset1.save()
        self.asset3.save()
        self.assertEqual(len(self.asset3.tags.all()),1)
        self.assertIn("test_tag_1",self.asset3.display_tags)
        self.assertIn("diff_category",self.asset3.display_tags)       
        self.assertEqual(len(self.asset1.tags.all()),3)
        self.assertIn("test_tag_1",self.asset1.display_tags)
        self.assertIn("diff_category",self.asset1.display_tags) 

        # Add duplicate
        self.asset1.add_tag("test_tag_1","test_category")
        self.asset1.save()
        self.assertEqual(len(self.asset1.tags.all()),3)
        self.assertIn("test_tag_1",self.asset1.display_tags)
        self.assertIn("test_category",self.asset1.display_tags)
        self.assertIn("test_tag_2",self.asset1.display_tags)   
        self.assertIn("test_category_2",self.asset1.display_tags)     
        self.assertIn("diff_category",self.asset1.display_tags) 


    def test_remove_tag(self):
        """
        Validates that the remove_tag function works as intended
        """
        
        # Remove existing
        self.asset1.add_tag("test_tag","test_category")
        self.asset2.add_tag("test_tag","test_category")
        self.asset1.save()
        self.asset2.save()
        self.assertEqual(len(self.asset1.tags.all()),1)
        self.assertEqual(len(self.asset2.tags.all()),1)
        self.asset1.remove_tag("test_tag","test_category")
        self.asset1.save()
        self.assertEqual(len(self.asset1.tags.all()),0)
        self.assertEqual(len(self.asset2.tags.all()),1)

        # Remove non-existing tag
        self.asset2.remove_tag("no_tag","no_category")
        self.asset2.save()
        self.assertEqual(len(self.asset2.tags.all()),1)

        # Remove tag that the asset doesn't have
        self.asset1.add_tag("new_tag","new_category")
        self.asset1.save()
        self.assertEqual(len(self.asset1.tags.all()),1)
        self.asset2.remove_tag("new_tag","new_category")
        self.asset2.save()
        self.assertEqual(len(self.asset2.tags.all()),1)

        # Remove non-existent tag with existing category
        self.asset2.remove_tag("fake_tag","test_category")
        self.asset2.save()
        self.assertEqual(len(self.asset2.tags.all()),1)

        # Remove existing tag non-existing category
        self.asset2.remove_tag("test_tag","fake_category")
        self.asset2.save()
        self.assertEqual(len(self.asset2.tags.all()),1)


    def test_has_tag(self):
        self.asset1.add_tag("test_tag_1","test_category_1")
        self.asset1.add_tag("test_tag_2","test_category_2")
        self.asset2.add_tag("test_tag_3","test_category_3")
        self.asset1.save()
        self.asset2.save()

        # Has tag
        self.assertTrue(self.asset1.has_tag("test_tag_1","test_category_1"))

        # Doesn't have tag
        self.assertFalse(self.asset1.has_tag("test_tag_3","test_category_3"))
        self.assertFalse(self.asset1.has_tag("FAKE","FAKE_CAT"))

        # has tag and has category, but not together
        self.assertFalse(self.asset1.has_tag("test_tag_2","test_category_1"))

        # Doesn't have tag but has category
        self.assertFalse(self.asset1.has_tag("FAKE","test_category_1"))

        # Doesn't have category, but has tag
        self.assertFalse(self.asset1.has_tag("test_tag_1","FAKE"))


    def test_split_tenable_os_and_version(self):
        # pattern x.x
        os = "Oracle Linux Server 9.8"
        os_2 = "Ubuntu 16.04.7 LTS (Xenial Xerus)"
        os, ver = self.asset1.__split_tenable_os_and_version(os)
        self.assertEqual("Oracle Linux Server",os)
        self.assertEqual("9.8", ver)
        os, ver = self.asset1.__split_tenable_os_and_version(os_2)
        self.assertEqual("Ubuntu",os)
        self.assertEqual("16.04.7", ver)

        # pattern x.x.x
        os = "macOS 15.7.1"
        os_2 = "Microsoft Windows Server 2012 R2 Standard 6.3.9600 0"
        os, ver = self.asset1.__split_tenable_os_and_version(os)
        self.assertEqual("macOS",os)
        self.assertEqual("15.7.1", ver)
        os, ver = self.asset1.__split_tenable_os_and_version(os_2)
        self.assertEqual("Microsoft Windows Server 2012 R2 Standard",os)
        self.assertEqual("6.3.9600", ver)

        # pattern x.x.x.x
        os = "Ubuntu 16.04.7.123451234 LTS (Xenial Xerus)"
        os, ver = self.asset1.__split_tenable_os_and_version(os)
        self.assertEqual("Ubuntu",os)
        self.assertEqual("16.04.7", ver)

        # pattern .x & x.ABC
        os = "Linux Kernel 5.x on Red Hat Enterprise Linux"
        os_2 = "Linux Kernel .12 on Red Hat Enterprise Linux"
        os, ver = self.asset1.__split_tenable_os_and_version(os)
        self.assertEqual("Linux Kernel 5.x on Red Hat Enterprise Linux",os)
        self.assertIsNone(ver)
        os, ver = self.asset1.__split_tenable_os_and_version(os_2)
        self.assertEqual("Linux Kernel .12 on Red Hat Enterprise Linux",os)
        self.assertIsNone(ver)

        # pattern abc
        os = "Cisco Device"
        os_2 = "Microsoft Windows Server 2003 R2 Service Pack 2"
        os, ver = self.asset1.__split_tenable_os_and_version(os)
        self.assertEqual("Cisco Device",os)
        self.assertIsNone(ver)
        os, ver = self.asset1.__split_tenable_os_and_version(os_2)
        self.assertEqual("Microsoft Windows Server 2003 R2 Service Pack 2",os)
        self.assertIsNone(ver)

        # debian edge case
        os = "Debian GNU/Linux 11 (bullseye)"
        os, ver = self.asset1.__split_tenable_os_and_version(os)
        self.assertEqual("Debian GNU/Linux",os)
        self.assertEqual("11",ver)

        # pattern abc.abc
        os = "macOS x.y.z"
        os_2 = "macOS x.y"

        os, ver = self.asset1.__split_tenable_os_and_version(os)
        self.assertEqual("macOS x.y.z",os)
        self.assertIsNone(ver)
        os, ver = self.asset1.__split_tenable_os_and_version(os_2)
        self.assertEqual("macOS x.y",os)
        self.assertIsNone(ver)

    def test_update_from_tenable_data(self):
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