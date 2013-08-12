# -*- coding: utf-8 -*-
"""Airplane related models."""
from __future__ import unicode_literals

import logging

from django.db import models
from django.utils.translation import ugettext_lazy as _


LOG = logging.getLogger(__name__)


class AirplaneType(models.Model):
    """
    A type an airplane can belong to.
    """

    title = models.CharField(_("name"), max_length=255,
        help_text=_("name of the type"))

    class Meta:
        verbose_name = _("airplane type")
        verbose_name_plural = _("airplane types")
        ordering = ('-id', )

    def __unicode__(self):
        return _("{0}").format(self.title)
