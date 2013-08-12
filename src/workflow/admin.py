# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import copy
import logging
import datetime

from functools import partial

from django import template
from django import forms
from django.db import models, transaction, router
from django.conf import settings
from django.conf.urls import patterns, url
from django.contrib import admin
from django.contrib.admin import helpers, options
from django.contrib.admin.util import unquote, quote, get_deleted_objects
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.generic import GenericInlineModelAdmin, GenericRelation
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.forms.formsets import all_valid
from django.forms.models import model_to_dict
from django.http import HttpResponseRedirect, HttpResponseNotFound, Http404
from django.shortcuts import get_object_or_404, render_to_response
from django.template.response import TemplateResponse
from django.utils.decorators import method_decorator
from django.utils.encoding import force_unicode, force_text
from django.utils.html import mark_safe, escape
from django.utils.text import capfirst
from django.utils.translation import ugettext as _
from django.views.decorators.csrf import csrf_protect

from workflow.models import Version
from workflow.constants import (
    VERSION_STATUS_NEED_ATTENTION, VERSION_STATUS_APPROVED, VERSION_STATUS_REJECTED, VERSION_STATUS_DRAFT,
    VERSION_TYPE_ADD, VERSION_TYPE_CHANGE, VERSION_TYPE_DELETE, VERSION_TYPE_RECOVER,
    VERSION_BRANCHES_MAX_COUNT)
from workflow.diff import changes_between_models, comment_from_changes
from workflow.security import is_user_content_admin, is_user_content_manager
from workflow.revisions import default_revision_manager, RegistrationError
from workflow.urls import (
    version_edit_url, version_view_changes_url, version_history_url, version_approve_url, version_reject_url)

csrf_protect_m = method_decorator(csrf_protect)

LOG = logging.getLogger(__name__)
STATIC_URL = getattr(settings, 'STATIC_URL', settings.MEDIA_URL)

class WorkflowAdmin(admin.ModelAdmin):

    # The revision manager instance used to manage revisions.
    revision_manager = default_revision_manager

    # The serialization format to use when registering models with reversion.
    reversion_format = 'json'

    # Whether to ignore duplicate revision data.
    ignore_duplicate_revisions = False

    change_list_template = 'workflow/change_list.html'
    change_form_template = 'workflow/change_form.html'
    object_history_template = 'workflow/object_history.html'
    version_edit_form_template = 'workflow/version_edit_form.html'
    view_changes_form_template = 'workflow/view_changes_form.html'
    recoverlist_template = 'workflow/recover_list.html'

    class Media:
        css = {
            'all': (STATIC_URL + 'workflow/css/workflow_admin.css', )
        }

    def _autoregister(self, model, follow=None):
        """Registers a model with reversion, if required."""
        if model._meta.proxy:
            raise RegistrationError("Proxy models cannot be used with django-reversion, register the parent class instead")
        if not self.revision_manager.is_registered(model):
            follow = follow or []
            for parent_cls, field in model._meta.parents.items():
                follow.append(field.name)
                self._autoregister(parent_cls)
            self.revision_manager.register(model, follow=follow, format=self.reversion_format)

    @property
    def revision_context_manager(self):
        """The revision context manager for this WorkflowAdmin."""
        return self.revision_manager._revision_context_manager

    def __init__(self, model, admin_site):
        super(WorkflowAdmin, self).__init__(model, admin_site)
        self.content_type = ContentType.objects.get_for_model(model)
        # Automatically register models if required.
        if not self.revision_manager.is_registered(self.model):
            inline_fields = []
            for inline in self.inlines:
                inline_model = inline.model
                if issubclass(inline, GenericInlineModelAdmin):
                    ct_field = inline.ct_field
                    ct_fk_field = inline.ct_fk_field
                    for field in self.model._meta.many_to_many:
                        if (isinstance(field, GenericRelation)
                        and field.rel.to == inline_model
                        and field.object_id_field_name == ct_fk_field
                        and field.content_type_field_name == ct_field):
                            inline_fields.append(field.name)
                    self._autoregister(inline_model)
                elif issubclass(inline, options.InlineModelAdmin):
                    fk_name = inline.fk_name
                    if not fk_name:
                        for field in inline_model._meta.fields:
                            if (isinstance(field, (models.ForeignKey, models.OneToOneField))
                            and issubclass(self.model, field.rel.to)):
                                fk_name = field.name
                    self._autoregister(inline_model, follow=[fk_name])
                    if not inline_model._meta.get_field(fk_name).rel.is_hidden():
                        accessor = inline_model._meta.get_field(fk_name).related.get_accessor_name()
                        inline_fields.append(accessor)
            self._autoregister(self.model, inline_fields)
        # Wrap own methods in manual revision management.
        self.add_view = self.revision_context_manager.create_revision(manage_manually=True)(self.add_view)
        self.change_view = self.revision_context_manager.create_revision(manage_manually=True)(self.change_view)
        self.delete_view = self.revision_context_manager.create_revision(manage_manually=True)(self.delete_view)
        self.recover_view = self.revision_context_manager.create_revision(manage_manually=True)(self.recover_view)
        self.revision_view = self.revision_context_manager.create_revision(manage_manually=True)(self.version_edit_view)
        self.changelist_view = self.revision_context_manager.create_revision(manage_manually=True)(self.changelist_view)

    def get_revision_instances(self, request, object):
        """Returns all the instances to be used in the object's revision."""
        return [object]

    def get_revision_data(self, request, object, flag):
        """Returns all the revision data to be used in the object's revision."""
        return dict(
            (o, self.revision_manager.get_adapter(o.__class__).get_version_data(o, flag))
            for o in self.get_revision_instances(request, object))

    def get_revision_form_data(self, request, obj, version):
        """
        Returns a dictionary of data to set in the admin form in order to revert
        to the given revision.
        """
        return version.field_dict

    def get_related_versions(self, obj, version, FormSet):
        """Retreives all the related Version objects for the given FormSet."""
        object_id = obj.pk
        # Get the fk name.
        try:
            fk_name = FormSet.fk.name
        except AttributeError:
            # This is a GenericInlineFormset, or similar.
            fk_name = FormSet.ct_fk_field.name
        # Look up the revision data.
        revision_versions = version.revision.version_set.all()
        related_versions = dict([(related_version.object_id, related_version)
                                 for related_version in revision_versions
                                 if ContentType.objects.get_for_id(related_version.content_type_id).model_class() == FormSet.model
                                 and force_text(related_version.field_dict[fk_name]) == force_text(object_id)])
        return related_versions

    def _hack_inline_formset_initial(self, FormSet, formset, obj, version):
        """Hacks the given formset to contain the correct initial data."""
        # if the FK this inline formset represents is not being followed, don't process data for it.
        # see https://github.com/etianen/django-reversion/issues/222
        if formset.rel_name not in self.revision_manager.get_adapter(self.model).follow:
            return

        # Now we hack it to push in the data from the revision!
        initial = []
        related_versions = self.get_related_versions(obj, version, FormSet)
        formset.related_versions = related_versions

        for related_version in related_versions.values():
            initial_row = related_version.field_dict
            pk_name = ContentType.objects.get_for_id(related_version.content_type_id).model_class()._meta.pk.name
            del initial_row[pk_name]
            initial.append(initial_row)

        for form in formset.forms:
            related_obj = form.save(commit=False)
            if related_obj.id == None:
                initial_data = model_to_dict(related_obj)
                pk_name = related_obj._meta.pk.name
                del initial_data[pk_name]
                if initial_data not in initial:
                    initial.append(initial_data)

        # Reconstruct the forms with the new revision data.
        formset.initial = initial
        formset.forms = [formset._construct_form(n) for n in range(len(initial))]
        # Hack the formset to force a save of everything.
        def get_changed_data(form):
            return [field.name for field in form.fields]
        for form in formset.forms:
            form.has_changed = lambda: True
            form._get_changed_data = partial(get_changed_data, form=form)
        def total_form_count_hack(count):
            return lambda: count
        formset.total_form_count = total_form_count_hack(len(initial))

    @csrf_protect_m
    @transaction.commit_on_success
    def add_view(self, request, form_url='', extra_context=None):
        extra_context = extra_context or {}
        # TODO: call content filler to set data about reversion
        extra_context['can_be_branched'] = False
        self.put_content_permissions(request, extra_context)
        return super(WorkflowAdmin, self).add_view(
            request, form_url, extra_context=extra_context)

    @csrf_protect_m
    @transaction.commit_on_success
    def change_view(self, request, object_id, form_url='', extra_context=None):
        "The 'change' admin view for this model."
        model = self.model
        opts = model._meta

        obj = self.get_object(request, unquote(object_id))

        if not self.has_change_permission(request, obj):
            raise PermissionDenied

        if obj is None:
            raise Http404(_('%(name)s object with primary key %(key)r does not exist.') % {'name': force_unicode(opts.verbose_name), 'key': escape(object_id)})

        if request.method == 'POST' and "_saveasnew" in request.POST:
            return self.add_view(request, form_url=reverse('admin:%s_%s_add' %
                                    (opts.app_label, opts.module_name),
                                    current_app=self.admin_site.name))

        ModelForm = self.get_form(request, obj)
        formsets = []
        inline_instances = self.get_inline_instances(request)

        version = Version.objects.latest_approved(self.content_type, object_id)
        if not version:
            version = self.create_initial_version(request, obj)
            messages.success(request, _("Initial object version created."))

        if request.method == 'POST':
            obj_copy = copy.deepcopy(obj)
            form = ModelForm(request.POST, request.FILES, instance=obj_copy)
            if form.is_valid():
                form_validated = True
                new_object = self.save_form(request, form, change=True)
            else:
                form_validated = False
                new_object = obj
            prefixes = {}
            for FormSet, inline in zip(self.get_formsets(request, new_object), inline_instances):
                prefix = FormSet.get_default_prefix()
                prefixes[prefix] = prefixes.get(prefix, 0) + 1
                if prefixes[prefix] != 1 or not prefix:
                    prefix = "%s-%s" % (prefix, prefixes[prefix])
                formset = FormSet(request.POST, request.FILES,
                                  instance=new_object, prefix=prefix,
                                  queryset=inline.queryset(request))
                formsets.append(formset)

            if all_valid(formsets) and form_validated:
                return self.process_common_post(
                    request, new_object, request.user, version.revision, form, formsets)
        else:
            form = ModelForm(instance=obj)
            prefixes = {}
            for FormSet, inline in zip(self.get_formsets(request, obj), inline_instances):
                prefix = FormSet.get_default_prefix()
                prefixes[prefix] = prefixes.get(prefix, 0) + 1
                if prefixes[prefix] != 1 or not prefix:
                    prefix = "%s-%s" % (prefix, prefixes[prefix])
                formset = FormSet(instance=obj, prefix=prefix,
                                  queryset=inline.queryset(request))
                formsets.append(formset)

        adminForm = helpers.AdminForm(form, self.get_fieldsets(request, obj),
            self.get_prepopulated_fields(request, obj),
            self.get_readonly_fields(request, obj),
            model_admin=self)
        media = self.media + adminForm.media

        inline_admin_formsets = []
        for inline, formset in zip(inline_instances, formsets):
            fieldsets = list(inline.get_fieldsets(request, obj))
            readonly = list(inline.get_readonly_fields(request, obj))
            prepopulated = dict(inline.get_prepopulated_fields(request, obj))
            inline_admin_formset = helpers.InlineAdminFormSet(inline, formset,
                fieldsets, prepopulated, readonly, model_admin=self)
            inline_admin_formsets.append(inline_admin_formset)
            media = media + inline_admin_formset.media

        context = {
            'title': _('Change %s') % force_unicode(opts.verbose_name),
            'adminform': adminForm,
            'object_id': object_id,
            'original': obj,
            'is_popup': "_popup" in request.REQUEST,
            'media': media,
            'inline_admin_formsets': inline_admin_formsets,
            'errors': helpers.AdminErrorList(form, formsets),
            'app_label': opts.app_label,
        }
        self.put_can_be_branched(request, object_id, context)
        self.put_content_permissions(request, context)
        context.update(extra_context or {})
        return self.render_change_form(request, context, change=True, obj=obj, form_url=form_url)


    @csrf_protect_m
    def changelist_view(self, request, extra_context=None):
        """Renders the changelist view."""
        opts = self.model._meta
        context = {
            'recoverlist_url': reverse("%s:%s_%s_recoverlist" % (
                self.admin_site.name, opts.app_label, opts.module_name)),
            'add_url': reverse("%s:%s_%s_add" % (
                self.admin_site.name, opts.app_label, opts.module_name)),}
        context.update(extra_context or {})
        return super(WorkflowAdmin, self).changelist_view(request, context)

    def recoverlist_view(self, request, extra_context=None):
        """Displays a list of deleted models to allow recovery."""
        # check if user has change or add permissions for model
        if not is_user_content_admin(request.user):
            raise PermissionDenied
        model = self.model
        opts = model._meta
        deleted = Version.objects.get_deleted(self.content_type)
        context = {
            'opts': opts,
            'app_label': opts.app_label,
            'module_name': capfirst(opts.verbose_name),
            'title': _("Deleted %(name)s") % {'name': force_text(opts.verbose_name_plural)},
            'deleted': deleted,
            'changelist_url': reverse("%s:%s_%s_changelist" % (
                self.admin_site.name, opts.app_label, opts.module_name)),
        }
        extra_context = extra_context or {}
        context.update(extra_context)
        return render_to_response(
            self.recoverlist_template, context, template.RequestContext(request))

    @transaction.commit_on_success
    def recover_view(self, request, version_id, extra_context=None):
        """Displays a form that can recover a deleted model."""
        # check if user has change or add permissions for model
        if not self.has_change_permission(request) and not self.has_add_permission(request):
            raise PermissionDenied
        version = get_object_or_404(Version, pk=version_id)
        obj = version.object_version.object
        context = {
            'title': _("Recovering %(name)s") % {'name': version.object_repr},
        }
        context.update(extra_context or {})
        return self.render_version_form(
            request, version, self.version_edit_form_template, context, recovering=True)

    def history_view(self, request, object_id, extra_context=None):
        object_id = unquote(object_id)
        opts = self.model._meta
        latest_approved_id = Version.objects.latest_approved(self.content_type, object_id).id
        action_list = [
            {
                'revision': version.revision,
                'edit_url': version_edit_url(version.object_id, version.id, self.admin_site.name, opts),
                'view_url': version_view_changes_url(version.object_id, version.id, self.admin_site.name, opts),
                'approve_url': version_approve_url(version.object_id, version.id, self.admin_site.name, opts),
                'reject_url': version_reject_url(version.object_id, version.id, self.admin_site.name, opts),
                'recover_url': reverse('%s:%s_%s_recover' % (
                    self.admin_site.name, opts.app_label, opts.module_name
                ), args=[version.id]),
                'is_current': version.id == latest_approved_id,
                'children_pks': version.revision.children.all().values_list('id', flat=True),
                'pending': version.revision.status == VERSION_STATUS_NEED_ATTENTION,
            }
            for version in Version.objects.filter(
                object_id=object_id,
                content_type=self.content_type
            ).select_related('revision', 'revision__changed_by', 'revision__moderated_by')
        ]
        context = {
            'action_list': action_list
            , 'is_admin': is_user_content_admin(request.user)
        }
        context.update(extra_context or {})
        return super(WorkflowAdmin, self).history_view(request, object_id, context)

    def render_version_form(self, request, version, form_template, extra_context, editing=False, recovering=False):
        obj = version.object_version.object
        object_id = obj.pk

        if (version.revision.deleted and version.revision.children.exists()):
            return HttpResponseNotFound(
                _(u"<p>Deleted object \"%s\" is already recovered. You cannot recover it again.</p>") % version)

        latest_approved = Version.objects.latest_approved(self.content_type, object_id)
        if (latest_approved.revision.deleted and not recovering):
            return HttpResponseNotFound(_(u"<p>You cannot view versions of deleted object.</p>"))

        model = self.model
        opts = model._meta
        v_opts = Version._meta

        ModelForm = self.get_form(request, obj)
        formsets = []

        is_approved = version.revision.status == VERSION_STATUS_APPROVED
        is_rejected = version.revision.status == VERSION_STATUS_REJECTED
        is_pending = version.revision.status == VERSION_STATUS_NEED_ATTENTION

        if request.method == 'POST':
            obj_copy = copy.deepcopy(obj)

            # This section is copied directly from the model admin change view
            # method.  Maybe one day there will be a hook for doing this better.
            form = ModelForm(request.POST, request.FILES, instance=obj_copy, initial=self.get_revision_form_data(request, obj_copy, version))
            if form.is_valid():
                form_validated = True
                new_object = self.save_form(request, form, change=True)
                # HACK: If the value of a file field is None, remove the file from the model.
                for field in new_object._meta.fields:
                    if isinstance(field, models.FileField) and field.name in form.cleaned_data and form.cleaned_data[field.name] is None:
                        setattr(new_object, field.name, None)
            else:
                form_validated = False
                new_object = obj
            prefixes = {}
            for FormSet, inline in zip(self.get_formsets(request, new_object),
                                       self.get_inline_instances(request)):
                prefix = FormSet.get_default_prefix()
                prefixes[prefix] = prefixes.get(prefix, 0) + 1
                if prefixes[prefix] != 1:
                    prefix = "%s-%s" % (prefix, prefixes[prefix])
                formset = FormSet(request.POST, request.FILES,
                                  instance=new_object, prefix=prefix,
                                  queryset=inline.queryset(request))
                self._hack_inline_formset_initial(FormSet, formset, obj, version)
                # Add this hacked formset to the form.
                formsets.append(formset)
            if all_valid(formsets) and form_validated:
                return self.process_common_post(
                    request, new_object, request.user, version.revision, form, formsets)
        else:
            # This is a mutated version of the code in the standard model admin
            # change_view.  Once again, a hook for this kind of functionality
            # would be nice.  Unfortunately, it results in doubling the number
            # of queries required to construct the formets.
            form = ModelForm(instance=obj, initial=self.get_revision_form_data(request, obj, version))
            prefixes = {}
            for FormSet, inline in zip(self.get_formsets(request, obj), self.get_inline_instances(request)):
                # This code is standard for creating the formset.
                prefix = FormSet.get_default_prefix()
                prefixes[prefix] = prefixes.get(prefix, 0) + 1
                if prefixes[prefix] != 1:
                    prefix = "%s-%s" % (prefix, prefixes[prefix])
                formset = FormSet(instance=obj, prefix=prefix,
                                  queryset=inline.queryset(request))
                self._hack_inline_formset_initial(FormSet, formset, obj, version)
                # Add this hacked formset to the form.
                formsets.append(formset)
        # Generate admin form helper.
        adminForm = helpers.AdminForm(form, self.get_fieldsets(request, obj),
            self.prepopulated_fields, self.get_readonly_fields(request, obj),
            model_admin=self)
        media = self.media + adminForm.media
        # Generate formset helpers.
        inline_admin_formsets = []
        for inline, formset in zip(self.get_inline_instances(request), formsets):
            fieldsets = list(inline.get_fieldsets(request, obj))
            readonly = list(inline.get_readonly_fields(request, obj))
            prepopulated = inline.get_prepopulated_fields(request, obj)
            inline_admin_formset = helpers.InlineAdminFormSet(inline, formset,
                fieldsets, prepopulated, readonly, model_admin=self)
            inline_admin_formsets.append(inline_admin_formset)
            media = media + inline_admin_formset.media

        if not recovering:
            if is_approved:
                messages.success(request, _("Current object was approved by admin."))
            elif is_rejected:
                messages.error(request, _("Current object was rejected by admin."))
            elif is_pending:
                messages.warning(request, _("Current object is waiting for admin approvement."))
            if version.revision.get_siblings().exclude(deleted=True).count() and (version.revision.parent is not None):
                messages.warning(request, _("Current object has an alternative version."))

        # Generate the context.
        context = {
            'title': _("Edit %(name)s") % {'name': obj},
            'adminform': adminForm,
            'object_id': object_id,
            'original': obj,
            'is_popup': False,
            'media': mark_safe(media),
            'inline_admin_formsets': inline_admin_formsets,
            'errors': helpers.AdminErrorList(form, formsets),
            'app_label': opts.app_label,
            'add': False,
            'change': True,
            'has_add_permission': self.has_add_permission(request),
            'has_change_permission': self.has_change_permission(request, obj),
            'has_delete_permission': self.has_delete_permission(request, obj),
            'has_file_field': True,
            'has_absolute_url': False,
            'ordered_objects': opts.get_ordered_objects(),
            'form_url': mark_safe(request.path),
            'opts': opts,
            'content_type_id': self.content_type.id,
            'save_as': False,
            'save_on_top': self.save_on_top,
            'changelist_url': reverse("%s:%s_%s_changelist" % (
                self.admin_site.name, opts.app_label, opts.module_name)),
            'change_url': reverse("%s:%s_%s_change" % (
                self.admin_site.name, opts.app_label, opts.module_name), args=(quote(obj.pk),)),
            'changes_url': version_view_changes_url(obj.pk, version.pk, self.admin_site.name, opts),

            'edit_url': version_edit_url(obj.pk, version.pk, self.admin_site.name, opts),
            'parent_url': version_edit_url(
                obj.pk, version.revision.parent.version(obj.pk, self.content_type).pk, self.admin_site.name, opts
            ) if version.revision.parent else None,
            'history_url': version_history_url(obj.pk, self.admin_site.name, opts),
            'delete_url': reverse("%s:%s_%s_delete" % (
                self.admin_site.name, v_opts.app_label, v_opts.module_name), args=(quote(version.pk),)),
            'working_with_version': True,
            'has_children': version.revision.children.exists(),
            'is_recovering': recovering,
            'is_approved': is_approved,
            'is_rejected': is_rejected,
            'is_pending': is_pending,
            'moderator_old_comment': version.revision.comment,
        }

        context.update(extra_context or {})
        self.put_can_be_branched(request, object_id, context, version)
        self.put_content_permissions(request, context)
        return render_to_response(form_template, context, template.RequestContext(request))

    @csrf_protect_m
    @transaction.commit_on_success
    def version_edit_view(self, request, object_id, version_id, extra_context=None):
        version = get_object_or_404(Version, pk=version_id)
        context = {
            'title': _("Edit version of %(name)s") % {'name': version.object_repr},
        }
        context.update(extra_context or {})
        return self.render_version_form(
            request, version, self.version_edit_form_template, context, editing=True)

    @csrf_protect_m
    @transaction.commit_on_success
    def version_changes_view(self, request, object_id, version_id, extra_context=None):
        version = get_object_or_404(Version, pk=version_id)
        parent = version.revision.parent
        if parent is not None and not parent.deleted:
            new_object = version.object_version.object
            old_object = parent.version(new_object.id, self.content_type).object_version.object
            changes = changes_between_models(
                old_object, new_object).values()
        else:
            changes = {}
        context = {
            'title': _("Viewing changes of %(name)s") % {'name': version.object_repr},
            'change_status_only': True,
            'changes': changes,
        }
        context.update(extra_context or {})
        return self.render_version_form(request, version, self.view_changes_form_template, context)

    def version_status_change_view(self, request, object_id, version_id, status, extra_context=None):
        revision = get_object_or_404(Version, pk=version_id).revision
        latest_approved_revision = Version.objects.latest_approved(self.content_type, object_id).revision
        if (revision.status == VERSION_STATUS_NEED_ATTENTION):
            revision.status = status
            revision.update_moderation(request.user)
            revision.save()
            if status == VERSION_STATUS_APPROVED:
                revision.revert(latest_approved_revision)
        return HttpResponseRedirect(version_history_url(object_id, self.admin_site.name, self.model._meta))

    @transaction.commit_on_success
    def version_status_approve_view(self, request, object_id, version_id, extra_context=None):
        return self.version_status_change_view(request, object_id, version_id, VERSION_STATUS_APPROVED, extra_context)

    @transaction.commit_on_success
    def version_status_reject_view(self, request, object_id, version_id, extra_context=None):
        return self.version_status_change_view(request, object_id, version_id, VERSION_STATUS_REJECTED, extra_context)

    def put_content_permissions(self, request, context):
        current_user = request.user
        context['has_content_manager_permission'] = is_user_content_manager(current_user)
        context['has_content_admin_permission'] = is_user_content_admin(current_user)

    def put_can_be_branched(self, request, object_id, context, version=None):
        has_children, can_be_branched = Version.objects.children_info(
            object_id=object_id,
            content_type=self.content_type,
            version=version)
        if has_children:
            if can_be_branched:
                messages.warning(
                    request,
                    _("Current object has more fresh versions in history."))
            else:
                messages.error(
                    request,
                    _("Current object already has {max_count} unapproved versions"
                        " and cannot be changed."
                    ).format(max_count=VERSION_BRANCHES_MAX_COUNT))
        context['can_be_branched'] = can_be_branched

    def create_initial_version(self, request, object):
        return self.revision_manager.save_revision(
            self.get_revision_data(request, object, VERSION_TYPE_ADD),
            user = request.user,
            comment = _(u"Initial version."),
            status = VERSION_STATUS_APPROVED,
            ignore_duplicates = self.ignore_duplicate_revisions,
            db = self.revision_context_manager.get_db()
        ).version(object.pk, self.content_type)

    def log_addition(self, request, object):
        """Sets the version meta information."""
        super(WorkflowAdmin, self).log_addition(request, object)
        self.create_initial_version(request, object);

    def delete_model(self, request, obj):
        """
        Given a model instance delete it from the database.
        """
        self.revision_manager.save_revision(
            self.get_revision_data(request, obj, VERSION_TYPE_DELETE),
            parent = Version.objects.latest_approved(self.content_type, obj.pk).revision,
            user = request.user,
            comment = _(u"Object is deleted."),
            delete = True,
            status = VERSION_STATUS_APPROVED,
            ignore_duplicates = self.ignore_duplicate_revisions,
            db = self.revision_context_manager.get_db(),
        )
        obj.delete()

    def process_common_post(self, request, obj, moderator, revision, form, formsets):
        latest_approved_revision = Version.objects.latest_approved(self.content_type, obj.pk).revision
        comment = request.POST.get("moderator_new_comment", "")

        changes = False
        if formsets:
            for formset in formsets:
                changes = (hasattr(formset, 'new_objects')
                    or hasattr(formset, 'changed_objects')
                    or hasattr(formset, 'deleted_objects'))
                if changes:
                    break
        changes = changes or form.has_changed()

        status_changed = False
        if request.POST.has_key("_reject"):
            status_changed = True
            revision.status = VERSION_STATUS_REJECTED
            if comment:
                revision.comment = comment
        if request.POST.has_key("_approve"):
            status_changed = True
            if changes:
                if revision.status == VERSION_STATUS_NEED_ATTENTION:
                    # TODO: can be branged?
                    revision.status = VERSION_STATUS_DRAFT
                    revision.update_moderation(moderator)
                    revision.save()
                self.save_with_relations(request, obj, form, formsets)
                revision = self.revision_manager.save_revision(
                    self.get_revision_data(request, obj, VERSION_TYPE_CHANGE),
                    parent = revision,
                    user = moderator,
                    comment = comment,
                    status = VERSION_STATUS_APPROVED,
                    ignore_duplicates = self.ignore_duplicate_revisions,
                    db = self.revision_context_manager.get_db(),)
            else:
                revision.status = VERSION_STATUS_APPROVED
                revision.revert(latest_approved_revision)
        if status_changed:
            revision.update_moderation(moderator)
            revision.save()
            return HttpResponseRedirect(
                version_history_url(obj.id, self.admin_site.name, self.model._meta))

        if request.POST.has_key('_recover'):
            self.save_with_relations(request, obj, form, formsets)
            revision = self.revision_manager.save_revision(
                self.get_revision_data(request, obj, VERSION_TYPE_RECOVER),
                parent = revision,
                user = moderator,
                comment = _(u"Deleted object was recovered."),
                status = VERSION_STATUS_APPROVED,
                ignore_duplicates = self.ignore_duplicate_revisions,
                db = self.revision_context_manager.get_db(),
            )
            return HttpResponseRedirect(
                version_edit_url(
                    obj.id, revision.version(obj.id, self.content_type).pk, self.admin_site.name, self.model._meta))

        if request.POST.has_key('_toapprove'):
            if changes or revision.status == VERSION_STATUS_REJECTED:
                self.save_with_relations(request, obj, form, formsets)
                revision_parent = revision
                revision = self.revision_manager.save_revision(
                    self.get_revision_data(request, obj, VERSION_TYPE_CHANGE),
                    user = request.user,
                    comment = comment,
                    parent = revision_parent,
                    ignore_duplicates = self.ignore_duplicate_revisions,
                    db = self.revision_context_manager.get_db(),
                )
                if (revision_parent.status == VERSION_STATUS_NEED_ATTENTION):
                    revision_parent.status = VERSION_STATUS_DRAFT
                    revision_parent.save()
                latest_approved_revision.revert(revision)
            if revision.status != VERSION_STATUS_APPROVED:
                revision.status = VERSION_STATUS_NEED_ATTENTION
                revision.save()
            return HttpResponseRedirect(
                version_edit_url(obj.id, revision.version(obj.id, self.content_type).pk, self.admin_site.name, self.model._meta))

        if request.POST.has_key('_tohistory'):
            if changes:
                self.save_with_relations(request, obj, form, formsets)
                revision = self.revision_manager.save_revision(
                    self.get_revision_data(request, obj, VERSION_TYPE_CHANGE),
                    user = request.user,
                    comment = comment,
                    parent = revision,
                    ignore_duplicates = self.ignore_duplicate_revisions,
                    db = self.revision_context_manager.get_db(),
                )
                latest_approved_revision.revert(revision)
                return HttpResponseRedirect(
                    version_edit_url(
                        obj.id, revision.version(obj.id, self.content_type).pk, self.admin_site.name, self.model._meta))
            else:
                return HttpResponseRedirect(".")

        if any(i in request.POST.keys() for i in ["_addanother", "_continue", "_save"]):
            auto_approve = is_user_content_admin(moderator)

            # TODO: improve changes detection for inlines and save only if changes were done
            self.save_with_relations(request, obj, form, formsets)
            if changes:
                # self.save_with_relations(request, obj, form, formsets)
                revision = self.revision_manager.save_revision(
                    self.get_revision_data(request, obj, VERSION_TYPE_CHANGE),
                    user = request.user,
                    comment = comment,
                    parent = revision,
                    status = VERSION_STATUS_APPROVED if auto_approve else VERSION_STATUS_DRAFT,
                    ignore_duplicates = self.ignore_duplicate_revisions,
                    db = self.revision_context_manager.get_db(),
                )
                if not auto_approve:
                    latest_approved_revision.revert(revision)
                return HttpResponseRedirect(reverse('admin:%s_%s_change' %
                    (obj._meta.app_label, obj._meta.module_name),
                    args=(obj.id,),
                    current_app=self.admin_site.name))
            elif auto_approve:
            # TODO: improve changes detection for inlines and use this instead of current elif statement:
            # elif auto_approve and (revision.children.exists() or revision.status == VERSION_STATUS_REJECTED):
                revision = self.revision_manager.save_revision(
                    self.get_revision_data(request, obj, VERSION_TYPE_CHANGE),
                    user = request.user,
                    comment = comment,
                    parent = revision,
                    status = VERSION_STATUS_APPROVED,
                    ignore_duplicates = self.ignore_duplicate_revisions,
                    db = self.revision_context_manager.get_db(),
                )
                return HttpResponseRedirect(reverse('admin:%s_%s_change' % (
                    obj._meta.app_label, obj._meta.module_name),
                    args=(obj.id,),
                    current_app=self.admin_site.name))

        return HttpResponseRedirect(".")

    def save_with_relations(self, request, obj, form, formsets):
        self.save_model(request, obj, form, change=True)
        form.save_m2m()
        for formset in formsets:
            # HACK: If the value of a file field is None, remove the file from the model.
            related_objects = formset.save(commit=False)
            for related_obj, related_form in zip(related_objects, formset.saved_forms):
                for field in related_obj._meta.fields:
                    if (isinstance(field, models.FileField)
                    and field.name in related_form.cleaned_data
                    and related_form.cleaned_data[field.name] is None):
                        setattr(related_obj, field.name, None)
                related_obj.save()
            formset.save_m2m()

    def get_urls(self):
        """Returns the additional urls used by the workflow admin."""
        urls = super(WorkflowAdmin, self).get_urls()
        admin_site = self.admin_site
        opts = self.model._meta
        info = opts.app_label, opts.module_name,
        reversion_urls = patterns("",
            url("^([^/]+)/edit/([^/]+)/$", admin_site.admin_view(self.version_edit_view),
                name='%s_%s_edit' % info),
            url("^([^/]+)/changes/([^/]+)/$", admin_site.admin_view(self.version_changes_view),
                name='%s_%s_changes' % info),
            url("^([^/]+)/approve/([^/]+)/$", admin_site.admin_view(self.version_status_approve_view),
                name='%s_%s_approve' % info),
            url("^([^/]+)/reject/([^/]+)/$", admin_site.admin_view(self.version_status_reject_view),
                name='%s_%s_reject' % info),
            url("^recover/([^/]+)/$", admin_site.admin_view(self.recover_view),
                name='%s_%s_recover' % info),
            url("^recover/$", admin_site.admin_view(self.recoverlist_view),
                name='%s_%s_recoverlist' % info),
        )
        return reversion_urls + urls

class VersionAdmin(admin.ModelAdmin):
    changelist_view_template = "workflow/version_change_list.html"

    @csrf_protect_m
    def changelist_view(self, request, extra_context=None):
        action_list = []

        for version in Version.objects.filter(
            revision__status=VERSION_STATUS_NEED_ATTENTION,
        ).select_related('revision', 'revision__created_by'):
            url_params = (version.object_id, version.id, self.admin_site.name, version.object_version.object._meta)
            try:
                action_list.append({
                    'version': version,
                    'edit_url': version_edit_url(*url_params),
                    'view_url': version_view_changes_url(*url_params),
                    'approve_url': version_approve_url(*url_params),
                    'reject_url': version_reject_url(*url_params),
                })
            except:
                pass
        context = {
            'title': force_unicode(self.model._meta.verbose_name_plural),
            'action_list': action_list,
        }
        context.update(extra_context or {})
        return render_to_response(
            self.changelist_view_template, context, template.RequestContext(request))

    @csrf_protect_m
    @transaction.commit_on_success
    def delete_view(self, request, object_id, extra_context=None):
        "The 'delete' admin view for this model."
        opts = self.model._meta
        app_label = opts.app_label

        obj = self.get_object(request, unquote(object_id))

        if not self.has_delete_permission(request, obj):
            raise PermissionDenied

        if obj is None:
            raise Http404(_('%(name)s object with primary key %(key)r does not exist.') % {'name': force_unicode(opts.verbose_name), 'key': escape(object_id)})

        using = router.db_for_write(self.model)

        # Populate deleted_objects, a data structure of all related objects that
        # will also be deleted.
        (deleted_objects, perms_needed, protected) = get_deleted_objects(
            [obj], opts, request.user, self.admin_site, using)

        if request.POST: # The user has already confirmed the deletion.
            if perms_needed:
                raise PermissionDenied
            raw_obj = obj.object_version.object
            obj_display = force_unicode(obj)
            self.log_deletion(request, obj, obj_display)
            self.delete_model(request, obj)

            self.message_user(request, _('The %(name)s "%(obj)s" was deleted successfully.')
                % {'name': force_unicode(opts.verbose_name), 'obj': force_unicode(obj_display)})

            if not self.has_change_permission(request, None):
                return HttpResponseRedirect(reverse('admin:index',
                                                    current_app=self.admin_site.name))
            return HttpResponseRedirect(
                version_history_url(raw_obj.id, self.admin_site.name, raw_obj._meta))

        object_name = force_unicode(opts.verbose_name)

        if perms_needed or protected:
            title = _("Cannot delete %(name)s") % {"name": object_name}
        else:
            title = _("Are you sure?")

        context = {
            "title": title,
            "object_name": object_name,
            "object": obj,
            "deleted_objects": deleted_objects,
            "perms_lacking": perms_needed,
            "protected": protected,
            "opts": opts,
            "app_label": app_label,
        }
        context.update(extra_context or {})

        return TemplateResponse(request, self.delete_confirmation_template or [
            "admin/%s/%s/delete_confirmation.html" % (app_label, opts.object_name.lower()),
            "admin/%s/delete_confirmation.html" % app_label,
            "admin/delete_confirmation.html"
        ], context, current_app=self.admin_site.name)

    def delete_model(self, request, obj):
        revision = obj.revision
        for version in revision.version_set.all():
            version.delete()
        revision.delete()

admin.site.register(Version, VersionAdmin)


