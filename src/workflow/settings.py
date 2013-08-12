# -*- coding: utf-8 -*-
"""
Settings for workflow app.
"""
from __future__ import unicode_literals
import os

from django.conf import settings


CONTENT_ADMIN_GRP_ID = getattr(settings, 'CONTENT_ADMIN_GRP_ID', '1')
CONTENT_MANAGER_GRP_ID = getattr(settings, 'CONTENT_MANAGER_GRP_ID', '2')
