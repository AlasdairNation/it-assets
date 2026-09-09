from django.db import models
from django.core.validators import RegexValidator

from organisation.models import DepartmentUser
from itsystems.models import ITSystemRecord


class AssetOwner(models.Model):
    """
    Represnts the organisational owner of an asset.
    Usually a branch or unit, ie; OIM
    """

    class Meta:
        verbose_name = "Owner"
        verbose_name_plural = "Owners"

    name = models.CharField(max_length=255, unique=True, verbose_name="Name")

    def __str__(self):
        return self.name

class Asset(models.Model):
    """
    Represents a physical or digital asset owned by the organisation.
    IE; a server, a user device, a web app, etc
    """

    class Meta:
        verbose_name = "Asset"
        verbose_name_plural = "Assets"

    TYPE_CHOICES = {
        "UD": "User Device",
        "S": "Server",
        "CI": "Container Image",
        "ND": "Network Device",
        "WA": "Web Application",
        "M": "Misc",
        "U": "Unknown"
    }

    name = models.CharField(max_length=255, unique=True, verbose_name="Name")
    aliases = models.JSONField(
        verbose_name="Alternate names",
        default = list,
        null = True,
        blank = True,
        editable = False
    )
    asset_type = models.CharField(
        max_length=2,
        choices=TYPE_CHOICES,
        default="U",
        verbose_name="Asset Type"
    )
    description = models.TextField(null=True, blank=True, verbose_name="Description")
    owner = models.ForeignKey(
        AssetOwner,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Owner",
        related_name="asset_owner_of",
        help_text="The unit / branch responsible for this asset"
    )
    contacts = models.ManyToManyField(
        DepartmentUser,
        blank=True,
        verbose_name="Contacts",
        related_name="asset_contact_of",
        help_text="The department user(s) to contact for a technical request"
    )
    systems = models.ManyToManyField(
        ITSystemRecord,
        blank=True,
        verbose_name="Associated IT Systems",
        related_name="related_assets",
        help_text="IT Systems that use this asset",
    ) 
    # Char field for now, but later could be a Foreign key field, with each OS being added as a distinct object dynamically
    os = models.CharField(
        max_length=255,
        verbose_name="OS",
        null=True,
        blank=True
    )
    os_version = models.CharField(
        max_length=255,
        verbose_name="OS Version",
        null=True,
        blank=True,
        validators= [
            RegexValidator(
                regex=r"^(?:$|(?:(\d+)\.)?(?:(\d+)\.)?(\d+))$",
                message="Invalid OS Version formatting. Please use format Int[.Int[.Int]], ie; '24.04', '12.6.03', etc).",
                code="invalid_os_version"
            )
        ]          
    )
    first_seen = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="First Seen"
    )
    last_seen = models.DateTimeField(
        verbose_name="Last Seen"
    )
    last_modified = models.DateTimeField(
        auto_now=True,
        verbose_name="Last Modified"
    )
    asset_defender_data = models.JSONField(
        default=dict,
        null=True,
        blank=True,
    )
    asset_tenable_data = models.JSONField(
        default=dict,
        null=True,
        blank=True,
    )

    @property
    def asset_contacts(self):
        return ", ".join([str(c) for c in self.contacts.all()])

    @property
    def associated_systems(self):
        return ", ".join([str(s) for s in self.systems.all()])

    @property
    def operating_system(self):
        displayString = self.os or ""
        if self.os_version:
            displayString += f" - {self.os_version}"
        return displayString


    def save(self, *args, **kwargs):
        """
        Overrides the default save method.
        This override converts empty string values to null values.
        """
        if self.description == "":
            self.description = None

        if self.os == "":
            self.os = None

        super(Asset, self).save(*args, **kwargs)

    def __str__(self):
        """
        Overrides the default __str__ method.
        """
        return self.name
