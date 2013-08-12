# -*- coding: utf-8 -*-
"""
Contains classes for the main dashboard and app index dashboard.
"""
from __future__ import unicode_literals

from django.utils.translation import ugettext_lazy as _
from django.conf import settings

from admin_tools.dashboard import modules, Dashboard, AppIndexDashboard


class ExampleIndexDashboard(Dashboard):
    """
    Custom index dashboard for project.
    """
    def init_with_context(self, context):

        #=======================================================================
        # Local applications
        #=======================================================================

        self.children.append(modules.ModelList(
            _("Airplanes"),
            draggable=True,
            deletable=False,
            collapsible=True,
            models=(
                'airplanes.models.*',
            )
        ))

        #=======================================================================
        # Configuration
        #=======================================================================

        config_models = (
            'django.contrib.auth.models.Group',
            'django.contrib.auth.models.User',
        )

        if settings.WORKFLOW_ENABLE:
            config_models = config_models + ('workflow.models.Version',)

        self.children.append(modules.ModelList(
            _("Configuration"),
            draggable=True,
            deletable=False,
            collapsible=True,
            models=config_models,
        ))

        #=======================================================================
        # Recent actions
        #=======================================================================

        self.children.append(modules.RecentActions(
            _('Recent Actions'),
            limit=10,
        ))


class ExampleAppIndexDashboard(AppIndexDashboard):
    """
    Custom app index dashboard for project.
    """

    # we disable title because its redundant with the model list module
    title = ''

    def __init__(self, *args, **kwargs):
        AppIndexDashboard.__init__(self, *args, **kwargs)
        # append a model list module and a recent actions module
        self.children += [
            modules.ModelList(self.app_title, self.models),
            modules.RecentActions(
                _('Recent Actions'),
                include_list=self.get_app_content_types(),
                limit=7
            ),
        ]

    def init_with_context(self, context):
        """
        Use this method if you need to access the request context.
        """
        return super(ExampleAppIndexDashboard, self).init_with_context(context)
