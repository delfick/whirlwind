Whirlwind
=========

A wrapper around the tornado web server.

Changlog
--------

.. _release-0-10-1:

0.10.1 - 8 January 2021
    * Removed the wait_for_futures helper. It's not a great implementation.
    * The server now uses ``await self.wait_for_end()`` to wait till we should
      shut down the server. By default this does ``await self.final_future`` like it
      already was doing.

.. _release-0-10-0:

0.10.0 - 25 October 2020
    * Removed whirlwind.test_helpers

      * It was random and didn't work well in an async context
      * Used asynctest which has warnings past python3.7 and isn't necessary anymore

.. _release-0-9-0:

0.9.0 - 10 May 2020
    * The SimpleWebSocketBase and WSHandler handlers now take in a
      ``final_future`` which is used to stop the websocket stream when it is
      cancelled.
    * Websocket streams that take in child messages will now use the request
      future on the websocket to know when to stop.

.. _release-0-8-0:

0.8.0 - 12 March 2020
    * The status of a response when there is an exception will now look at:

      * If the msg is a dictionary, it'll get "status" from that dictionary if it has that
      * If the exception has a "status" property, the status will be that value
      * Otherwise the status will be 500

.. _release-0-7-2:

0.7.2 - 6 March 2020
    * Fix a small mistake that meant http handlers weren't logging even if
      ``log_exceptions=False`` wasn't specified.

.. _release-0-7-1:

0.7.1 - 6 March 2020
    * Made it possible to accept files into a commander command. You can do this
      by sending a ``multipart/form-data`` to the endpoint. The body of the
      command will be extracted from a ``__body__`` file you provide.
    * HTTP and WebSocket handlers can now be told not to log exceptions by giving
      them a class level ``log_exceptions = False`` attribute.

.. _release-0-7:

0.7 - 3 February 2020
    * Made transform_progress responsible for name spacing the progress messages
    * Store commands can now be interactive. If you define the execute method as
      taking in ``messages``, then you can process extra messages sent to that
      command. You then define what messages it accepts by using the
      ``store.command`` decorator with the ``parent`` option as the interactive
      command.
    * Reusing a command with a different path is now an error

.. _release-0-6:

0.6 - 18 September 2019
    * Migrated to `delfick_project <https://delfick-project.readthedocs.io/en/latest/index.html>`_

.. _release-0-5.3:

0.5.3 - Dec 26 2018
    * WSHandler now has a connection_future that is cancelled if we lose the
      connection

.. _release-0-5.2:

0.5.2 - Oct 25 2018
    * Added a message_done hook to SimpleWebSocketBase
    * Fixed the test helpers so that you aren't left with no set asyncio loop

.. _release-0-5.1:

0.5.1 - Oct 24 2018
    * Made the ``__server_time__`` message for SimpleWebSocketBase optional.
    * Made sure to actually use the reprer set on request handlers
    * ProgressMessageMaker doesn't nest dictionaries it receives
    * Added a transform_progress hook to SimpleWebSocketBase

.. _release-0-5:

0.5 - Oct 22 2018
    * Initial Release

Installation
------------

This package is released to pypi under the name ``whirlwind-web``. When you add
this package to your setup.py it is recommended you either specify ``[peer]`` as
well or pin ``input_algorithms``, ``option_merge`` and ``tornado`` to particular
versions.  See https://github.com/delfick/whirlwind/blob/main/setup.py#L24-L28
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
