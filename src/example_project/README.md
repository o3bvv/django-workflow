example_project
===============

Quickstart
----------

To bootstrap the project::

    virtualenv example_project
    source example_project/bin/activate
    cd path/to/example_project/repository
    pip install -r requirements.pip
    pip install -e .
    cp example_project/settings/local.py.example example_project/settings/local.py
    manage.py syncdb --migrate

Documentation
-------------

Developer documentation is available in Sphinx format in the docs directory.

Initial installation instructions (including how to build the documentation as
HTML) can be found in docs/install.rst.
