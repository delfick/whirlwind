.. _handlers:

Request Handlers
================

There are two main types of request handlers that whirlwind provide, ``Simple``
and ``SimpleWebSocketBase`` for http and websockets respectively. There's nothing
that forces you to use these classes, but they do provide some benefits.

Simple Request Handler
----------------------

To use this class you do something like:

.. code-block:: python

  from whirlwind.request_handlers.base import Simple

  class MyRequestHandler(Simple):
      async def do_get(self):
          return {"hello": "world"}

      async def do_put(self):
          body = self.body_as_json()
          return {"echo": body}

Simple will use ``do_get``, ``do_put``, ``do_post``, ``do_patch`` and ``do_delete``
for each of the HTTP methods. If the handler receives a method that isn't
implemented it will return a 405 response. These hooks are all ``async`` functions.

If the method returns a string that starts with ``<html>`` or ``<!DOCTYPE html>``
then it returns the response with a ``Content-Type`` of ``text/html``. If the
result is a ``dict`` or ``list`` then it will turn the result into a JSON string
and provide the ``Content-Type`` as ``application/json; charset=UTF-8``.

Otherwise it will just write the return to the response and provide the
``Content-Type`` as ``text/plain; charset=UTF-8``.

Converting objects to JSON
--------------------------

When converting the result to a JSON object it will convert the object such that
``byte`` objects are converted using ``binascii.hexlify(obj)`` and anything else
that isn't JSON serializable is converted using ``repr(obj)``. You can modify
this behaviour by setting a different ``reprer`` on the handler. For example:

.. code-block:: python

  class Thing:
      def __str__(self):
          return "thing as a string"
  
  class MyRequstHandler(Simple):
      def initialize(self, thing):
          super().initialize()
          self.thing = thing

          def other_reprer(o):
              """Convert non json'able objects into strings"""
              return str(o)
          self.reprer = other_reprer
      
      async def do_get(self):
          return {"thing": self.thing}

  class Server(Server):
      def tornado_routes(self):
          return [("/one", MyRequestHandler, {"thing": Thing()})]

  await Server(asyncio.Future()).serve("0.0.0.0", 9001)

  # curl http://0.0.0.0:9001/one will return {"thing": "thing as a string"}

Converting exceptions to messages
---------------------------------

The other thing that these handlers do is convert exceptions into messages for
the response. It will use the ``message_from_exc`` function on the handler to
convert the exception to a message and then the conversion rules for a normal
returned object from the handler apply to this message.

By default ``message_from_exc`` will treat ``whirlwind.request_handlers.base.Finished``
exceptions as a special case and return an ``InternalServerError`` for everything
else.

For example:

.. code-block:: python

  from whirlwind.request_handlers.base import Finished, Simple
  from whirlwind.server import Server
  
  class Handler1(Simple):
      async def do_get(self):
          raise Finished(status=400, detail="information")

  class Handler2(Simple):
      async def do_get(self):
          raise ValueError("Bad")

  class Server(Server):
      def tornado_routes(self):
          return [
                ("/one", handler1)
              , ("/two", Handler2)
              ]

  # curl /one returns a 400 response that says
  # {"status": 400, "detail": "information"}

  # curl /two returns a 500 response that says
  # {"status": 500, "error_code": "InternalServerError", "error": "Internal Server Error"}

If you want to modify how exceptions are turned into messages then you give the
handler a new ``message_from_exc`` callable. This is a function that takes in
``exception_type, exception, traceback``, which is the information you get from
calling ``sys.exc_info()``.

If you want to keep the existing behaviour, then you can subclass the
``whirlwind.request_handlers.base.MessageFromExc`` class. For example:

.. code-block:: python

  from whirlwind.request_handlers.base import Finished, Simple, MessageFromExc
  from whirlwind.server import Server

  class WhoAreYou(Exception):
      pass

  class MyMessageFromExc(MessageFromExc):
      def process(self, exc_type, exc, tb):
          """This hook is used if the exception is not a Finished exception"""
          if isinstance(exc_type, WhoAreYou):
              return {"status": "401", "error_code": exc_type.__name__, "error": "Couldn't identify you"}
          return super().process(exc_type, exc, tb)
  
  class Handler(Simple):
      def initialize(self):
          super().initialize()
          self.message_from_exc = MyMessageFromExc()

      async def do_get(self):
          raise WhoAreYou()

  class Server(Server):
      def tornado_routes(self):
          return [("/one", handler)]

  # curl /one returns a 401 response that says
  # {"status": 401, "error_code": "WhoAreYou", "error": "Couldn't identify you"}

Websocket Handler
-----------------

The other request handler type is the ``SimpleWebSocketBase`` which lets you
create a websocket handler. For example:

.. code-block:: python

  from whirlwind.request_handlers.base import SimpleWebSocketBase
  from whirlwind.server import wait_for_futures, Server

  import time

  class WSHandler(SimpleWebSocketBase):
      async def process_message(self, path, body, message_id, message_key, progress_cb):
          progress_cb({"called_path": path, "called_body": body})
          return {"success": True}

  class Server(Server):
      async def setup(self):
          self.wsconnections = {}

      def tornado_routes(self):
          return [
                ( "/ws"
                , WSHandler
                , {"server_time": time.time(), "wsconnections": self.wsconnections}
                )
              ]

      async def cleanup(self):
          # Wait for our websockets to finish
          await wait_for_futures(self.wsconnections)

  # Opening the websocket stream to /ws will get us back this message
  # {"reply": <the server_time>, "message_id": "__server_time__"}
  # unless you supply server_time as None, in which case it won't send server_time

  # Then when we send the message {"path": "/somewhere, "body": {"something": True}, "message_id": "message1"}
  # We get back the following two messages
  # {"message_id": "message1", "reply": {"progress": {"called_path": "/somewhere", "called_body": {"something": True}}}
  # {"message_id": "message1", "reply": {"success": True}}

Everything about how the replies and exceptions are treated (and the reprer and
message_from_exc functions) are the same for the websocket handler.

The handler is opinionated however and will complain if your messages are not of
the form ``{"path": <string>, "body": <value>, "message_id": <string>}``. Also
all replies are of the form ``{"message_id": <message_id from request>, "reply": <object>}``

When you call the ``progress_cb`` callback the reply will be of the form
``{"message_id": <message_id_from-request>, "reply": {"progress": <object given to progress_cb}}``

Also, the Websocket handler takes in ``server_time`` and ``wsconnections`` as
parameters. The ``server_time`` is used to tell the client the time at which the
server was started. This is so the client can determine if the server was changed
since the last time it started a websocket stream with the server. If you supply
server_time as None then it won't send this message.

The ``wsconnections`` object is used to store the asyncio tasks that are created
for each websocket message that is received. It is up to you to wait on these
tasks when the server is finished to ensure they finish cleanly. The ``wait_for_futures``
helper does just this, as shown in the example. The handler will create a unique
uuid for every message it receives and use that as the key in ``wsconnections``.
This unique uuid is passed into ``process_message`` as ``message_key``.

The other thing that this handler will do for you is handle any message of the
form ``{"path": "__tick__", "message_id": "__tick__"}`` with the reply of
``{"message_id": "__tick__", "reply": {"ok": "thankyou"}}``. This is so clients
can keep the connection alive by sending such messages every so often.
