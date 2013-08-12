# -*- coding: utf-8 -*-
"""
Module contains init_workflow management command.
"""
from __future__ import unicode_literals

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.utils.translation import ugettext_lazy as _

from workflow.settings import CONTENT_ADMIN_GRP_ID, CONTENT_MANAGER_GRP_ID


class Command(BaseCommand):
    """A management command which initializes workflow."""

    help = "Initialize workflow"

    def handle(self, *args, **kwargs):
        self.init_group_and_user(
            "testca",
            (CONTENT_ADMIN_GRP_ID, "ContentAdmins"))
        self.init_group_and_user(
            "testcm",
            (CONTENT_MANAGER_GRP_ID, "ContentManagers"))

    def init_group_and_user(self, user_login, group_info):
        grp, created = Group.objects.get_or_create(
            pk=group_info[0],
            name=group_info[1])
        self.init_user(user_login, grp)

    def init_user(self, login, group):
        usr, created = User.objects.get_or_create(
            username=login,
            email= "%s@life.ua" % login,
            is_staff=True,
            is_active=True)
        usr.set_password(login)
        usr.groups.add(group)
        usr.save()
