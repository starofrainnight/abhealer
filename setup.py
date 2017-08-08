#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

with open('README.rst') as readme_file, open('HISTORY.rst') as history_file:
    long_description = (readme_file.read() + "\n\n" + history_file.read())

requirements = [
    'click>=6.0',
    'jinja2',
    'pyyaml',
]

test_requirements = [
    # TODO: put package test requirements here
]

setup(
    name='abhealer',
    version='0.2.4',
    description="abhealer",
    long_description=long_description,
    author="Hong-She Liang",
    author_email='starofrainnight@gmail.com',
    url='https://github.com/starofrainnight/abhealer',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'abhealer=abhealer.__main__:main'
        ]
    },
    include_package_data=True,
    install_requires=requirements,
    license="Apache Software License",
    zip_safe=False,
    keywords='abhealer',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    test_suite='tests',
    tests_require=test_requirements
)
