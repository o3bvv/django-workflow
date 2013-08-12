# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.utils.translation import ugettext as _


VERSION_BRANCHES_MAX_COUNT = 10

VERSION_STATUS_DRAFT = 'DR'
VERSION_STATUS_NEED_ATTENTION = 'NA'
VERSION_STATUS_APPROVED = 'AP'
VERSION_STATUS_REJECTED = 'RJ'

VERSION_STATUSES = (
    (VERSION_STATUS_DRAFT, _("Draft")),
    (VERSION_STATUS_NEED_ATTENTION, _("Needs attention")),
    (VERSION_STATUS_APPROVED, _("Approved")),
    (VERSION_STATUS_REJECTED, _("Rejected")),
)

VERSION_TYPE_ADD = 'ADD'
VERSION_TYPE_CHANGE = 'CHG'
VERSION_TYPE_DELETE = 'DEL'
VERSION_TYPE_RECOVER = 'RCV'

VERSION_TYPES = (
    (VERSION_TYPE_ADD, _("Adding")),
    (VERSION_TYPE_CHANGE, _("Changing")),
    (VERSION_TYPE_DELETE, _("Deleting")),
    (VERSION_TYPE_RECOVER, _("Recovering")),
)
