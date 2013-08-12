# -*- coding: utf-8 -*-
"""Admins for airplane related models."""
from __future__ import unicode_literals

import logging

from django.contrib import admin

from admin_custom.options import ModelAdmin
from airplanes.models import AirplaneType


LOG = logging.getLogger(__name__)


class AirplaneTypeAdmin(ModelAdmin):
    pass


admin.site.register(AirplaneType, AirplaneTypeAdmin)
