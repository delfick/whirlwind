Whirlwind
=========

A wrapper around the tornado web server.

Changlog
--------

0.5 - Oct 22 2018
    * Initial Release

Installation
------------

This package is released to pypi under the name ``whirlwind-web``. When you add
this package to your setup.py it is recommended you either specify ``[peer]`` as
well or pin ``input_algorithms``, ``option_merge`` and ``tornado`` to particular
versions.  See https://github.com/delfick/whirlwind/blob/master/setup.py#L24-L28
for the recommended versions.

For example:

.. code-block:: python


    from setuptools import setup, find_packages
    
    setup(
          name = "test"
        , version = "0.1"
        , include_package_data = True
    
        , install_requires =
          [ "whirlwind-web[peer]"
          , "whirlwind-web==0.5"
          ]
        )

Running the tests
-----------------

To run the tests, create and activate a virtualenv somewhere and then::

    $ pip install -e ".[peer,tests]"
    $ pip install -e .

followed by ``./test.sh``

Alternatively::
    
    $ pip install tox
    $ tox

Usage
-----

See https://whirlwind.readthedocs.io/en/latest/ for usage documentation.
