# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.utils.translation import ugettext_lazy as _
from workflow.settings import CONTENT_ADMIN_GRP_ID, CONTENT_MANAGER_GRP_ID


def is_user_content_admin(user):
	return user.groups.filter(pk=CONTENT_ADMIN_GRP_ID).exists() \
        or user.is_superuser


def is_user_content_manager(user):
	return user.groups.filter(pk=CONTENT_MANAGER_GRP_ID).exists()
