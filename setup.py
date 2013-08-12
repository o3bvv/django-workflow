# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

from version import __version__

dependencies = [
    "setuptools",
]

setup(
    name="django-workflow",
    version='.'.join(str(x) for x in __version__),
    description="Django web framework extension which provides models workflow control facilities",
    long_description=open("README.md").read(),
    keywords="django models workflow",
    license="MIT",
    author_email="oblovatniy@gmail.com",
    url="https://github.com/oblalex/django-workflow",
    bugtrack_url="https://github.com/oblalex/django-workflow/issues",
    packages = find_packages("src"),
    package_dir = {"": "src"},
    include_package_data=True,
    zip_safe=False,
    install_requires=dependencies,
    classifiers = [
        "Development Status :: 4 - Beta",
        "Topic :: Software Development :: Libraries",
        "Intended Audience :: Developers",
        "Environment :: Web Environment",
        "Programming Language :: Python",
        "Framework :: Django",
        "Operating System :: OS Independent",
        "Natural Language :: English",
        "License :: OSI Approved :: MIT License",
    ],
)
