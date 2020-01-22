#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='pyvantage',
    version='0.0.1',
    license='MIT',
    description='Grammar-based language for Home Assistant and converter to YAML.'
    author='Greg J. Badros',
    author_email='badros@gmail.com',
    url='http://github.com/gjbadros/hass-hgl-to-yaml',
    packages=find_packages(),
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Home Automation',
    ],
    install_requires=[],
    zip_safe=True,
)
