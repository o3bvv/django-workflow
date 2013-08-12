"""Base settings shared by all environments"""
# Import global settings to make it easier to extend settings.
from django.conf.global_settings import *   # pylint: disable=W0614,W0401

#==============================================================================
# Calculation of directories relative to the project module location
#==============================================================================

import os
import sys
import example_project as project_module

PROJECT_DIR = os.path.dirname(os.path.realpath(project_module.__file__))

PYTHON_BIN = os.path.dirname(sys.executable)
ve_path = os.path.dirname(os.path.dirname(os.path.dirname(PROJECT_DIR)))
# Assume that the presence of 'activate_this.py' in the python bin/
# directory means that we're running in a virtual environment.
if os.path.exists(os.path.join(PYTHON_BIN, 'activate_this.py')):
    # We're running with a virtualenv python executable.
    VAR_ROOT = os.path.join(os.path.dirname(PYTHON_BIN), 'var')
elif ve_path and os.path.exists(os.path.join(ve_path, 'bin',
        'activate_this.py')):
    # We're running in [virtualenv_root]/src/[project_name].
    VAR_ROOT = os.path.join(ve_path, 'var')
else:
    # Set the variable root to a path in the project which is
    # ignored by the repository.
    VAR_ROOT = os.path.join(PROJECT_DIR, 'var')
if not os.path.exists(VAR_ROOT):
    os.mkdir(VAR_ROOT)

LOG_ROOT = os.path.join(VAR_ROOT, 'log')
if not os.path.exists(LOG_ROOT):
        os.mkdir(LOG_ROOT)

APPS_ROOT = os.path.join(PROJECT_DIR, 'apps')
sys.path.append(APPS_ROOT)

#==============================================================================
# Generic Django project settings
#==============================================================================

DEBUG = True
TEMPLATE_DEBUG = DEBUG
WORKFLOW_ENABLE = True

SITE_ID = 1
# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
TIME_ZONE = 'UTC'
USE_TZ = True
USE_I18N = True
USE_L10N = True
LANGUAGE_CODE = 'en'
LANGUAGES = (
    ('en', 'English'),
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'o#ont%s#(&-3k6z1jk_-%a4f8&l%ud$x(^019n#sg4k19d25+t'

INSTALLED_APPS = (
    'admin_tools',
    'admin_tools.menu',
    'admin_tools.dashboard',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'django.contrib.admindocs',

    # 3rd-party applications
    'south',
    'workflow',

    # Local applications
    'website',
)

#==============================================================================
# Project URLS and media settings
#==============================================================================

ROOT_URLCONF = 'example_project.urls'

LOGIN_URL = '/login/'
LOGOUT_URL = '/logout/'
LOGIN_REDIRECT_URL = '/'

STATIC_URL = '/static/'
MEDIA_URL = '/uploads/'

STATIC_ROOT = os.path.join(VAR_ROOT, 'static')
MEDIA_ROOT = os.path.join(VAR_ROOT, 'uploads')

STATICFILES_DIRS = (
    os.path.join(PROJECT_DIR, 'static'),
)

#==============================================================================
# Templates
#==============================================================================

TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
)

TEMPLATE_DIRS = (
    os.path.join(PROJECT_DIR, 'templates'),
)

TEMPLATE_CONTEXT_PROCESSORS += (
    'django.core.context_processors.request',
    'django.contrib.auth.context_processors.auth',
)

#==============================================================================
# Fixtures
#==============================================================================

FIXTURE_DIRS = (
#   'website/fixtures/',
)

#==============================================================================
# Middleware
#==============================================================================

MIDDLEWARE_CLASSES += (
)

#==============================================================================
# Auth / security
#==============================================================================

AUTHENTICATION_BACKENDS += (
)

#==============================================================================
# Miscellaneous project settings
#==============================================================================

#==============================================================================
# Third party app settings
#==============================================================================

# Django admin tools
ADMIN_TOOLS_INDEX_DASHBOARD = 'admin_custom.dashboard.ExampleIndexDashboard'
ADMIN_TOOLS_APP_INDEX_DASHBOARD = \
    'admin_custom.dashboard.ExampleAppIndexDashboard'
ADMIN_TOOLS_MENU = 'admin_custom.menu.ExampleMenu'
