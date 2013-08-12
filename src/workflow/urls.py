from django.conf.urls import patterns
from django.core.urlresolvers import reverse
from django.contrib.admin.util import quote

# URL patterns for workflow

urlpatterns = patterns('workflow.views',
    # Add url patterns here
)


def version_edit_url(object_id, version_id, site_name, opts):
    return reverse("%s:%s_%s_edit" % (
        site_name, opts.app_label, opts.module_name),
        args=(quote(object_id), quote(version_id),))


def version_view_changes_url(object_id, version_id, site_name, opts):
    return reverse("%s:%s_%s_changes" % (
        site_name, opts.app_label, opts.module_name),
        args=(quote(object_id), quote(version_id),))


def version_approve_url(object_id, version_id, site_name, opts):
    return reverse("%s:%s_%s_approve" % (
        site_name, opts.app_label, opts.module_name),
        args=(quote(object_id), quote(version_id),))


def version_reject_url(object_id, version_id, site_name, opts):
    return reverse("%s:%s_%s_reject" % (
        site_name, opts.app_label, opts.module_name),
        args=(quote(object_id), quote(version_id),))


def version_history_url(object_id, site_name, opts):
    return reverse("%s:%s_%s_history" % (
        site_name, opts.app_label, opts.module_name),
        args=(quote(object_id),))
