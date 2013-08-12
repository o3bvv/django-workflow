# -*- coding: utf-8 -*-
"""
Base admin models.
"""
from __future__ import unicode_literals

from django.conf import settings
from django.contrib.admin import ModelAdmin as DefaultAdmin


try:
    from workflow.admin import WorkflowAdmin
    AdminBase = WorkflowAdmin if settings.WORKFLOW_ENABLE else DefaultAdmin
except ImportError:
    AdminBase = DefaultAdmin


class ModelAdmin(AdminBase):
    pass
