.. _server:

The Server
==========

Whirlwind provides the ``whirlwind.server.Server`` class for creating a tornado
web server and handling the life cycle of the server.

The simplest case is if you don't have any setup requirements, for example:

.. code-block:: python

  from whirlwind.server import Server

  from tornado.web import StaticFileHandler
  import asyncio

  class MyServer(Server):
      def tornado_routes(self):
          return [
                ( r"/static/(.*)"
                , StaticFileHandler
                , {"path": "/path/to/assets"
                )
              ]

  final_future = asyncio.Future()
  server = MyServer(final_future)

  host = "0.0.0.0"
  port = 9001
  await server.serve(host, port)

This will start a server on ``http://0.0.0.0:9001`` that serves ``/path/to/assets``
under the path ``/static``. It will keep serving until our ``final_future`` is
finished. Note that in our example above, that never happens. In a real
application you would manage the final_future so say it cancels on a SigTERM.

Extra setup
-----------

If you need to create extra objects for your routes then you can implement the
``setup`` hook. If you also need to run shutdown logic for your extra objects
then you can implement the ``cleanup`` hook which will run after the server has
stopped.

.. code-block:: python

  from my_application import MyRouteHandler, Thing

  from whirlwind.server import Server

  import asyncio

  class MyServer(Server):
      async def setup(self, argument1, argument2):
          self.thing = Thing(argument1, argument2)
          await self.thing.setup()

      async def cleanup(self):
          await self.thing.cleanup()

      def tornado_routes(self):
          return [
                ( r"/one/(.*)"
                , MyRouteHandler
                , {"thing": self.thing
                )
              ]

  final_future = asyncio.Future()
  server = MyServer(final_future)

  host = "0.0.0.0"
  port = 9001
  await server.serve(host, port, "argument1", argument2=3)

The positional and keyword arguments after the ``host`` and ``port`` that are
provided to ``serve`` will be passed into the ``setup`` function.

Setttings for the tornado.web.Application
-----------------------------------------

We create the web server by saying:

.. code-block:: python

    async def serve(self, host, port, *args, **kwargs):
        server_kwargs = await self.setup(*args, **kwargs)
        if server_kwargs is None:
            server_kwargs = {}

        http_server = HTTPServer(tornado.web.Application(self.tornado_routes(), **server_kwargs))

This means if you have extra arguments to provide to the Application then you
can just return them from the setup function. For example if I wanted to setup
a cookie secret:

.. code-block:: python

  class MyServer(Server):
      async def setup(self, cookie_secret):
          return {"cookie_secret": cookie_secret}

  MyServer(asyncio.Future()).serve("0.0.0.0", 9001, "sup3rs3cr3t")
