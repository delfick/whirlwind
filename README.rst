Whirlwind
=========

A wrapper around the tornado web server.

Changlog
--------

0.7.2 - 6 March 2020
    * Fix a small mistake that meant http handlers weren't logging even if
      ``log_exceptions=False`` wasn't specified.

0.7.1 - 6 March 2020
    * Made it possible to accept files into a commander command. You can do this
      by sending a ``multipart/form-data`` to the endpoint. The body of the
      command will be extracted from a ``__body__`` file you provide.
    * HTTP and WebSocket handlers can now be told not to log exceptions by giving
      them a class level ``log_exceptions = False`` attribute.

0.7 - 3 February 2020
    * Made transform_progress responsible for name spacing the progress messages
    * Store commands can now be interactive. If you define the execute method as
      taking in ``messages``, then you can process extra messages sent to that
      command. You then define what messages it accepts by using the
      ``store.command`` decorator with the ``parent`` option as the interactive
      command.
    * Reusing a command with a different path is now an error

0.6 - 18 September 2019
    * Migrated to `delfick_project <https://delfick-project.readthedocs.io/en/latest/index.html>`_

0.5.3 - Dec 26 2018
    * WSHandler now has a connection_future that is cancelled if we lose the
      connection

0.5.2 - Oct 25 2018
    * Added a message_done hook to SimpleWebSocketBase
    * Fixed the test helpers so that you aren't left with no set asyncio loop

0.5.1 - Oct 24 2018
    * Made the ``__server_time__`` message for SimpleWebSocketBase optional.
    * Made sure to actually use the reprer set on request handlers
    * ProgressMessageMaker doesn't nest dictionaries it receives
    * Added a transform_progress hook to SimpleWebSocketBase

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
          , "whirlwind-web==0.5.2"
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
