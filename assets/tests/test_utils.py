from django.test import TestCase

from assets.utils import alias_get_or_create
from assets.models import Asset
from assets.tests.test_model import RandomAssetGenerator as Gen

class UtilsTestCase(TestCase):
    def test_alias_get_or_create(self):
        """
        Tests that alias_get_or_create works as intended
        """
        asset1, asset2 = Gen().generate(2)
        asset1.aliases = ["name1", "name2", "name3"]
        asset2.aliases = ["test1","test1.name.domain","name3"]
        asset1.save()
        asset2.save()

        # Test no new assets are created for a device with an existing alias
        self.assertEqual(len(Asset.objects.all()),2)
        new_asset, created = alias_get_or_create(aliases=["name1", "blah blah", "woah"])
        self.assertEqual(created,False)
        self.assertEqual(new_asset.pk,asset1.pk)
        self.assertEqual(len(Asset.objects.all()),2)

        # Tests that a new asset is created for a device without an existing alias
        new_asset, created = alias_get_or_create(aliases=["name", "new", "new2"])
        self.assertEqual(created, True)
        self.assertNotEqual(new_asset.pk,asset1.pk)
        self.assertNotEqual(new_asset.pk,asset2.pk)
        self.assertEqual(len(Asset.objects.all()),3)

        # Tests that the first asset found is returned when other aliases match others
        new_asset, created = alias_get_or_create(aliases=["name1", "name", "tester3"])
        self.assertEqual(created, False)
        self.assertEqual(new_asset.pk,asset1.pk)
        self.assertEqual(len(Asset.objects.all()),3)

        # Tests that when multiple assets share the same alias, only the first found is returned
        new_asset, created = alias_get_or_create(aliases=["name3"])
        self.assertEqual(created, False)
        self.assertTrue(new_asset.pk == asset1.pk or new_asset.pk == asset2.pk)
        self.assertEqual(len(Asset.objects.all()),3)

