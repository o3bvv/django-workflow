# -*- coding: utf-8 -*-
"""Database models used by workflow."""
from __future__ import unicode_literals

import datetime
import logging

from mptt.models import MPTTModel

from django.dispatch.dispatcher import Signal
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.conf import settings
from django.core import serializers
from django.db import models
from django.db.models import F
from django.utils.encoding import force_text
from django.utils.translation import ugettext_lazy as _

from workflow.constants import (
    VERSION_STATUSES, VERSION_STATUS_DRAFT, VERSION_STATUS_APPROVED,
    VERSION_TYPES, VERSION_TYPE_ADD, VERSION_TYPE_DELETE,
    VERSION_BRANCHES_MAX_COUNT)

LOG = logging.getLogger(__name__)


def has_int_pk(model):
    """Tests whether the given model has an integer primary key."""
    pk = model._meta.pk
    return (
        (
            isinstance(pk, (models.IntegerField, models.AutoField)) and
            not isinstance(pk, models.BigIntegerField)
        ) or (
            isinstance(pk, models.ForeignKey) and has_int_pk(pk.rel.to)
        )
    )


def safe_revert(versions):
    """
    Attempts to revert the given models contained in the give versions.

    This method will attempt to resolve dependencies between the versions to revert
    them in the correct order to avoid database integrity errors.
    """
    unreverted_versions = []
    for version in versions:
        try:
            version.revert()
        except (IntegrityError, ObjectDoesNotExist):
            unreverted_versions.append(version)
    if len(unreverted_versions) == len(versions):
        raise RevertError("Could not revert revision, due to database integrity errors.")
    if unreverted_versions:
        safe_revert(unreverted_versions)


class Revision(MPTTModel):
    """
    A version of a revision of related objects including
    admin inlines and many-to-many relationships
    """
    parent = models.ForeignKey(
        'self',
        verbose_name=_('Parent'),
        blank=True, null=True,
        related_name='children')
    date_created = models.DateTimeField(
        auto_now_add=True, editable=False,
        verbose_name=_("date created"),
        help_text="The date and time a version was created.")
    created_by = models.ForeignKey(
        User, blank=True, null=True,
        editable=True, related_name='created_by_set')
    date_moderated = models.DateTimeField(
        editable=False, blank=True, null=True,
        verbose_name=_("date moderated"),
        help_text="The date and time a version was moderated.")
    moderated_by = models.ForeignKey(
        User, blank=True, null=True,
        editable=False, related_name='moderated_by_set')
    comment = models.TextField(
        blank=True,
        verbose_name=_("comment"),
        help_text="A text comment on this version.")
    status = models.CharField(
        _("статус версии"),
        max_length=2,
        choices=VERSION_STATUSES,
        default=VERSION_STATUS_DRAFT)
    deleted = models.BooleanField(
        default=False,
        help_text="Specifies if revision is deleted.")
    manager_slug = models.CharField(
        max_length = 200,
        db_index = True,
        default = "default")

    def version(self, id, content_type):
        return self.version_set.get(object_id=id, content_type=content_type)

    def revert(self, previous=None, delete=False):
        """Reverts all objects in this revision."""
        version_set = self.version_set.all()

        if previous:
            for v in previous.version_set.exclude(object_id__in=self.version_set.values_list('object_id')):
                v.object_version.object.delete()

        # Optionally delete objects no longer in the current revision.
        if delete:
            # Get a dict of all objects in this revision.
            old_revision = {}
            for version in version_set:
                try:
                    obj = version.object
                except ContentType.objects.get_for_id(version.content_type_id).model_class().DoesNotExist:
                    pass
                else:
                    old_revision[obj] = version
            # Calculate the set of all objects that are in the revision now.
            from reversion.revisions import RevisionManager
            current_revision = RevisionManager.get_manager(self.manager_slug)._follow_relationships(obj for obj in old_revision.keys() if obj is not None)
            # Delete objects that are no longer in the current revision.
            for item in current_revision:
                if item in old_revision:
                    if old_revision[item].object_type == VERSION_TYPE_DELETE:
                        item.delete()
                else:
                    item.delete()
        # Attempt to revert all revisions.
        safe_revert([version for version in version_set if version.object_type != VERSION_TYPE_DELETE])

    def update_moderation(self, moderator):
        self.date_moderated = datetime.datetime.now()
        self.moderated_by = moderator

    def __unicode__(self):
        return ", ".join(force_text(version)
            for version in self.version_set.all())

    class Meta:
        verbose_name = _(u"Objects group version")
        verbose_name_plural = _(u"Objects group versions")
        ordering = ['-date_created']


class VersionManager(models.Manager):
    """
    Custom manager for Version model.
    """
    def latest_approved(self, content_type, object_id):
        try:
            return Version.objects.filter(
                object_id=object_id,
                content_type=content_type,
                revision__status=VERSION_STATUS_APPROVED
            ).latest('revision__date_moderated')
        except Version.DoesNotExist:
            return None

    def children_info(self, content_type, object_id, version=None):
        """
        Returns tuple: (has_children, can_be_branched)
        """
        if not version:
            version = self.latest_approved(content_type, object_id)
        children_count = version.revision.children.count() if version else 0
        return (children_count > 0, children_count < VERSION_BRANCHES_MAX_COUNT)

    def get_deleted(self, content_type):
        return Version.objects.filter(
            content_type=content_type,
            revision__deleted=True,
            revision__lft=F('revision__rght')-1)


class Version(models.Model):
    """A saved version of a database model."""

    revision = models.ForeignKey(Revision,
        blank = False,
        null = False,
        help_text="The revision that contains this version.")
    object_id = models.TextField(
        help_text="Primary key of the model under version control.")
    object_id_int = models.IntegerField(
        blank = True,
        null = True,
        db_index = True,
        help_text = "An indexed, integer version of the stored model's primary key, used for faster lookups.",)
    content_type = models.ForeignKey(ContentType,
        related_name="workflow_version_ct")

    # A link to the current instance, not the version stored in this Version!
    object_link = generic.GenericForeignKey()

    format = models.CharField(
        max_length=255,
        help_text="The serialization format used by this model.")
    serialized_data = models.TextField(
        help_text="The serialized form of this version of the model.")
    object_repr = models.TextField(
        help_text="A string representation of the object.")
    object_type = models.CharField(
        _("version type"),
        max_length=3,
        choices=VERSION_TYPES,
        default=VERSION_TYPE_ADD)

    @property
    def object_version(self):
        """The stored version of the model."""
        data = self.serialized_data
        data = force_text(data.encode("utf8"))
        return list(serializers.deserialize(self.format, data, ignorenonexistent=True))[0]

    @property
    def field_dict(self):
        """
        A dictionary mapping field names to field values in this version
        of the model.

        This method will follow parent links, if present.
        """
        if not hasattr(self, "_field_dict_cache"):
            object_version = self.object_version
            obj = object_version.object
            result = {}
            for field in obj._meta.fields:
                result[field.name] = field.value_from_object(obj)
            result.update(object_version.m2m_data)
            # Add parent data.
            for parent_class, field in obj._meta.parents.items():
                content_type = ContentType.objects.get_for_model(parent_class)
                if field:
                    parent_id = force_text(getattr(obj, field.attname))
                else:
                    parent_id = obj.pk
                try:
                    parent_version = Version.objects.get(revision__id=self.revision_id,
                                                         content_type=content_type,
                                                         object_id=parent_id)
                except Version.DoesNotExist:
                    pass
                else:
                    result.update(parent_version.field_dict)
            setattr(self, "_field_dict_cache", result)
        return getattr(self, "_field_dict_cache")

    def revert(self):
        """Recovers the model in this version."""
        self.object_version.save()

    def __unicode__(self):
        return _("%s") % self.object_repr

    class Meta:
        verbose_name = _(u"Object version")
        verbose_name_plural = _(u"Object versions")
        ordering = ['-revision__date_created']

    objects = VersionManager()


# Version management signals.
pre_revision_commit = Signal(providing_args=["instances", "revision", "versions"])
post_revision_commit = Signal(providing_args=["instances", "revision", "versions"])
