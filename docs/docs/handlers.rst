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
