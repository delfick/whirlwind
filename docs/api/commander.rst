.. _commander:

The Commander
=============

Whirlwind also provides a thing called the ``Commander`` for splitting up your
request handler into many commands.

These commands can then have variables injected into them from what options you
provide the commander.

You create a ``store`` of these commands and then the commander knows how to
create a command from the arguments you give it and will execute that command.

An example in code:

.. code-block:: python

  from whirlwind.request_handlers.command import CommandHandler, WSHandler
  from whirlwind.server import Server, wait_for_futures
  from whirlwind.commander import Commander
  from whirlwind.store import Store

  from option_merge.formatter import MergedOptionStringFormatter
  from input_algorithms.dictobj import dictobj
  from input_algorithms import spec_base as sb
  import asyncio
  import signal
  import uuid
  import time

  class Formatter(MergedOptionStringFormatter):
      """
      knows how to get options from the commander

      It has two methods that need to be implemented, ``special_get_field`` and
      ``special_format_field``. These are used to create custom format modifiers.
      """
      def special_get_field(self, *args, **kwargs):
          pass

      def special_format_field(self, *args, **kwargs):
          pass

  # create the store, this holds onto all our commands
  # When we create a command, if we don't specify path, then default_path is used
  # A formatter must be provided if we want to be able to inject options into commands
  store = Store(default_path="/v1/commands", formatter=Formatter)

  @store.command("one")
  class One(store.Command):
      async def execute(self):
          return {"one": True}

  @store.command("two")
  class Two(store.Command):
      # Inject option1 from our commander
      # This is provided to the commander when we create it further down
      option1 = store.injected("option1")

      async def execute(self):
          # We can access options on self
          return {"option": self.option1}

  @store.command("three")
  class Three(store.Command):
      # We can add fields that get taken from args the command was executed with
      # See https://input-algorithms.readthedocs.io
      value = dictobj.Field(sb.string_spec, wrapper=sb.required)

      async def execute(self):
          return {"value": self.value}

  @store.command("four")
  class Four(store.Command):
      # The progress_cb makes most sense for when we execute a command via a websocket
      # It is a callback that'll send back a progress message to the connection
      # If we execute this command via a HTTP request handler nothing will happen
      progress_cb = store.injected("progress_cb")

      async def execute(self):
          self.progress_cb({"hello": "there"})
          return {"good": "bye"}

  class S(Server):
      async def setup(self, option1):
          self.wsconnections = {}
          self.commander = Commander(store
              , option1=option1
              )

      async def cleanup(self):
          await wait_for_futures(self.wsconnections)

      def tornado_routes(self):
          return [
                ( "/v1/commands"
                , CommandHandler
                , {"commander": self.commander}
                )
              , ( "/v1/ws"
                , WSHandler
                , { "commander": self.commander
                  , "server_time": time.time()
                  , "wsconnections": self.wsconnections
                  }
                )
              ]

  loop = asyncio.get_event_loop()

  # The server listens to final_future and will stop when it's cancelled
  final_future = asyncio.Future()
  loop.add_signal_handler(signal.SIGTERM, final_future.cancel)

  server = S(final_future)

  # Things added to the commander can be anything
  # Here we're giving option1 as a string, to the server so it can add it to
  # the commander. I could also create this in setup, but I'm demonstrating how
  # to pass things in when we call serve
  option1 = str(uuid.uuid1())
  loop.run_until_complete(server.serve("127.0.0.1", 8000, option1))

This server we have created allows ``PUT`` requests on ``/v1/commands`` and
websocket connections over ``/v1/ws``.

The shape of the body for the ``PUT`` requests must be
``{"command": <command>, "args": <args>}``. Command will line up to the name of
each command. In our example we have commands for ``one``, ``two`` , ``three``
and ``four``.

Messages to the websocket handler must be of the form
``{"path": "/v1/commands", "body": {"command": <command>, "args": <args>}, "message_id": <message_id>}``
and will do the same as our PUT commands, but with the added benefit of getting
progress messages.

In both cases ``args`` is optional and defaults to an empty dictionary.

So in our examples above:

PUT /v1/commands ``{"command": "one"}``
  Returns JSON ``{"one": True}``

PUT /v1/commands ``{"command": "two"}``
  Returns JSON ``{"option": <option1>}``

PUT /v1/commands ``{"command": "three"}``
  Returns an internal server error because we are missing a required option.

  You can return a better error by overriding the ``message_from_exc`` option
  on your request handlers. For example

  .. code-block:: python

    from whirlwind.request_handlers.base import MessageFromExc

    class MyMessageFromExc(MessageFromExc):
        def process(self, exc_type, exc, tb):
            """This hook is used if the exception is not a Finished exception"""
            if hasattr(exc, "as_dict"):
                return {"status": 400, "error": exc.as_dict()}
            return super().process(exc_type, exc, tb)

    class CommandHandler(CommandHandler):
        def initialize(self, *args, **kwargs):
            super().initialize(*args, **kwargs)
            self.message_from_exc = MyMessageFromExc()

    class WSHandler(WSHandler):
        def initialize(self, *args, **kwargs):
            super().initialize(*args, **kwargs)
            self.message_from_exc = MyMessageFromExc()

  If you did that, then the return would be:

  .. code-block:: json

    {
        "error": {
            "errors": [
                {
                    "message": "Bad value. Expected a value but got none",
                    "meta": "{path=<input>.body.args.value}"
                }
            ],
            "message": "Bad value",
            "meta": "{path=<input>.body.args}"
        },
        "status": 400
    }

PUT /v1/commands ``{"command": "three", "args": {"value": "yo"}}``
  returns JSON ``{"value": "yo"}``

PUT /v1/commands ``{"command": "four"}``
  returns JSON ``{"good": "bye"}``

WS /v1/ws
  Opening the websocket connection gets us the server time ``{'reply': 1540095155.917255, 'message_id': '__server_time__'}``

  Sending ``{"path": "/v1/commands", "body": {"command": "three", "args": {"value": "yo"}}, "message_id": "uniqueidentity"}``
  Replies with two messages:

  * ``{"reply": {"progress": {"hello": "there"}}, "message_id": "uniqueidentity"}``
  * ``{"reply": {"good": "bye"}, "message_id": "uniqueidentity"}``

Available Variables
-------------------

Each command can have injected any variable added to the commander as well as
the following variables:

path
  The path that was used to reach this command

store
  The store used to get this command

executor
  This is an object with an ``execute`` method on it for executing other commands.
  Anything available to be injected into this command will be available for any
  command you execute with this.

  For example:

  .. code-block:: python

    @store.command("one")
    class One(store.Command):
        value = dictobj.Field(sb.integer_spec)

        async def execute(self):
            return {"value": value}

    @store.command("two")
    class Two(store.Command):
        path = store.injected("path")
        executor = store.injected("executor")

        async def execute(self):
            return await self.executor.execute(self.path, {"command": "one", "args": {"value": 20}})

  Executing ``{"command": "two"}`` will return us ``{"value": 20}``.

progress_cb
  The progress_cb that was given to the executor. If you use the request handlers
  in ``whirlwind.request_handlers.command`` then this will do nothing for
  ``CommandHandler`` and will send progress messages in ``WSHandler``

request_future
  A future that is cancelled once the request is finished

request_handler
  The tornado request handler that accepted the request

When you call ``executor.execute`` you may also pass in a dictionary of ``extra_optinos``
which will override any option in the commander.

Changing progress_cb
--------------------

If you want to change how the progress_cb works then you can do something like:

.. code-block:: python

  from whirlwind.request_handlers.command import ProgressMessageMaker

  class MyProgressMessageMaker(ProgressMessageMaker):
      def do_log(self, body, message, info, **kwargs):
          """
          Called if ``do_log=True`` is provided to the ``progress_cb``

          body
            The body of the request or the "body" in the websocket message

          message
            The message provided to the progress_cb

          info
            The message transformed for returning in the progress_cb. You may
            override ``def make_info(self, body, message, **kwargs)`` to change
            what it gets turned into.

            By default:

            message = None
              Turned into ``{"done": True}``

            message is an Exception
              Turned into ``{"error": <message.as_dict() or str(message>, "error_code": message.__class__.__name__}``

            otherwise
              Turned into  ``{"info": <message>}``

            Any ``**kwargs`` given to ``progress_cb`` is added to ``info``.

          ``**kwargs``
            The extra keyword arguments given to the ``progress_cb``
          """

          # self.logger_name is the name of the module where ``progress_cb`` was
          # called from
          logging.getLogger(self.logger_name).info(json.dumps(info))

  class CommandHandler(CommandHandler):
      progress_maker = MyProgressMessageMaker

  class WSHandler(WSHandler):
      progress_maker = MyProgressMessageMaker

``progress_maker`` must be a callable that returns a callable that has the
signature ``def __call__(self, body, message, do_log=True, **kwargs)`` where
``body`` is the body of the request and ``message`` is the message to give back
as progress.

Sending files to a command
--------------------------

You can send files to a command by sending a normal ``multipart/form-data``
request. To also specify the body of the command you would normally send with
the PUT request, have a ``__body__`` file in your reqest.

You can then access the files by doing something like:

.. code-block:: python

    @store.command("my_command")
    class MyCOmmand(store.Command):
        handler = store.injected("handler")

        async def execute(self):
            fle = self.handler.request.files["my_attachment"][0]["body"]
            return {"my_attachment_size": len(fle)}
