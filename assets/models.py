import re

from django.db import models
from django.core.validators import RegexValidator
from django.utils.timezone import now


from organisation.models import DepartmentUser
from itsystems.models import ITSystemRecord


class AssetTagCategory(models.Model):
    class Meta:
        verbose_name = "Asset Tag Category"
        verbose_name_plural = "Asset Tag Categories"

    name = models.CharField(max_length=255, unique=True, verbose_name="Name")

    @classmethod
    def get_default_pk(cls):
        return AssetTagCategory.objects.get_or_create(name="Misc.")[0].pk

    def __str__(self):
        return self.name

    
class AssetTag(models.Model):
    class Meta:
        verbose_name = "Asset Tag"
        verbose_name_plural = "Asset Tags"

    tag_id = models.CharField(max_length=255,unique=True, editable=False)
    name = models.CharField(max_length=255, verbose_name="Name")
    category = models.ForeignKey(
        AssetTagCategory,
        on_delete=models.CASCADE,
        default=AssetTagCategory.get_default_pk,
        related_name="tags_within_category",
        help_text="Tag Category"
    )

    def save(self, *args, **kwargs):
        """
        Overrides the default save method.
        Auto-generates the tag_id.
        This should also enforce that tags are unique within their category.
        """
        self.tag_id = f"{self.name} - {self.category.name}"

        super(AssetTag, self).save(*args, **kwargs)


    def __str__(self):
        return f"{self.category.name}: {self.name}"

    

class Asset(models.Model):
    """
    Represents a physical or digital asset owned by the organisation.
    IE; a server, a user device, a web app, etc
    """

    class Meta:
        verbose_name = "Asset"
        verbose_name_plural = "Assets"

    tenable_id = models.CharField(max_length=255, unique=True, verbose_name="tenable_id", editable=False)
    name = models.CharField(max_length=255, unique=False, null=True, blank=True, verbose_name="Name")
    aliases = models.JSONField(
        verbose_name="Alternate names",
        default = list,
        null = True,
        blank = True,
        editable = False
    )
    description = models.TextField(null=True, blank=True, verbose_name="Description")
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
        verbose_name="Last Seen",
        null=True,
        blank=True,
    )
    last_modified = models.DateTimeField(
        auto_now=True,
        verbose_name="Last Modified"
    )
    defender_data = models.JSONField(
        default=dict,
        null=True,
        blank=True,
    )
    tenable_data = models.JSONField(
        default=dict,
        null=True,
        blank=True,
    )
    tags = models.ManyToManyField(
        AssetTag,
        blank=True,
        verbose_name="Tags",
        related_name="tagged_assets",
        help_text="Tenable Tags"
    )

    @property
    def asset_contacts(self):
        """Provides a string display version of contacts for the admin page."""
        return ", ".join([str(c) for c in self.contacts.all()])

    @property
    def associated_systems(self):
        """Provides a string display version of any associated IT Systems for the admin page"""
        return ", ".join([str(s) for s in self.systems.all()])

    @property
    def operating_system(self):
        """Provides a combined 'OS - Version' string for display"""
        displayString = self.os or ""
        if self.os_version:
            displayString += f" - {self.os_version}"
        return displayString

    @property
    def custodian(self) -> str:
        """
        Returns a string representation of the custodian tag.
        """
        return self.__get_tag_category_string("Custodian")

        
    @property
    def asset_type(self) -> str:
        """
        Returns a string representation of the device type tag.
        """
        return self.__get_tag_category_string("Devices")

    @property
    def display_tags(self) -> str:
        return ", ".join([f"{t.category.name}: {t.name}" for t in self.tags.all()])



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

    def update_from_tenable_data(self, tenable_data: dict | None = None):
        """
        Updates internal fields using data found in tenable_data.
        If passed tenable_data as a parameter, the model's internal tenable_data is overridden first.
        """
        # Override internal tenable_data if passed in.
        if tenable_data:
            self.tenable_data = tenable_data
            self.last_seen = now()

        # Update internal fields
        if self.tenable_data:
            t = self.tenable_data
            # Set ID
            self.tenable_id = t.get("id")
            # Retrieve Aliases
            aliases = []
            if t.get('network'):
                if t['network'].get('hostnames'):
                    aliases.append(t['network']['hostnames'][0].split(".")[0])
                    aliases.extend(t['network']['hostnames']) 
                if t['network'].get('fqdns'):
                    aliases.append(t['network']['fqdns'][0].split(".")[0])
                    aliases.extend(t['network']['fqdns'])
            if t.get('agent_names'):
                aliases.extend(t['agent_names'])  
            # Set name & aliases
            if aliases:
                self.name = aliases[0]
                self.aliases = list(set(self.aliases + aliases)) # merges without duplicates
            # Set OS & OS Version
            self.os, self.os_version = self.__split_tenable_os_and_version(t.get("operating_systems")[0]) if t.get("operating_systems") else (None, None)
            # Set tags
            if self.tenable_data.get("tags"):
                for tag in self.tenable_data.get("tags"):
                    self.add_tag(tag=tag["value"], category=tag["key"])

        self.save()

    def add_tag(self,tag: str, category: str):
        """
        Adds a tag to an asset. If the tag and/or category doesn't exist, they're created.
        """
        if not self.has_tag(tag,category):
            found_category, _ = AssetTagCategory.objects.get_or_create(name=category)
            found_tag, _ = AssetTag.objects.get_or_create(
                tag_id = f"{tag} - {category}",
                name = tag,
                category = found_category,
            )
            self.tags.add(found_tag)

    def has_tag(self,tag:str,category:str):
        return self.tags.filter(tag_id=f"{tag} - {category}").exists()
        

    def __split_tenable_os_and_version(self, os_string: str):
        """
        Converts a tenable OS string into an OS & version number.
        Returns a tuple of (OS <string>, version number <string>)
        """
        os, version = [None, None]
        if os_string:
            version_regex = r"\d+\.\d+(?:\.\d+)?" # Looks for Major.Minor or Major.Minor.Patch
            if "Debian" in os_string:
                version_regex = r"\d{1,2}" # Looks only for Major
            match = re.search(version_regex,os_string)
            if match: 
                os = re.split(version_regex, os_string)[0].strip()
                version = match.group().strip()
            elif "Build" in os_string:
                os = os_string.split("Build")[0].strip()
            elif os_string is not None or "":
                os = os_string
        return os, version



    def __get_tag_category_string(self, category: str) -> str:
        tags = [tag.name for tag in self.tags.filter(category__name=category)]
        return ", ".join(tags)


    def __str__(self):
        """
        Overrides the default __str__ method.
        """
        return str(self.name)
    
