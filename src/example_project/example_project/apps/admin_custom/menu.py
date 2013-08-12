# -*- coding: utf-8 -*-
"""
Contains custom menu for admin site.
"""
from __future__ import unicode_literals

from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

from admin_tools.menu import items, Menu


class ExampleMenu(Menu):
    """
    Custom Menu for admin site.
    """
    def __init__(self, **kwargs):
        Menu.__init__(self, **kwargs)
        self.children += [
            items.MenuItem(_('Dashboard'), reverse('admin:index')),
            items.Bookmarks(),
        ]

    def init_with_context(self, context):
        """
        Use this method if you need to access the request context.
        """
        return super(ExampleMenu, self).init_with_context(context)
