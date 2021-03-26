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

Server end future
-----------------

The ``final_future`` you provide the server is a future that is to be resolved when your
program has ended. Whirlwind will use this to know that it should stop the server.

However, it can be nice to end the server before the entire program, and so you can
define a separate future that is used instead.

.. code-block:: python

  final_future = asyncio.Future()
  server_end_future = asyncio.Future()

  # The server will end when server_end_future is finished instead of final_future
  server = MyServer(final_future, server_end_future=server_end_future)

Alternatively you may implement the ``wait_till_end`` method which returns when you
want the server to shutdown.

.. code-block:: python

  from whirlwind.server import Server
  import asyncio


  class ServerThatStopsAfterAMinute(Server):
      async def wait_till_end(self):
          # By default it's, ``await self.server_end_future``
          await asyncio.sleep(60)

Extra setup
-----------

If you need to create extra objects for your routes then you can implement the
``setup`` hook. If you also need to run shutdown logic for your extra objects
then you can implement the ``cleanup`` hook which will run after the server has
stopped.

.. code-block:: python

  from my_application import MyRouteHandler, Thing

  from tornado.httpserver import HTTPServer
  from whirlwind.server import Server
  import tornado.web
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
        self.server_kwargs = await self.setup(*args, **kwargs)
        if self.server_kwargs is None:
            self.server_kwargs = {}

        self.routes = self.tornado_routes()
        self.http_server = self.make_http_server(self.routes, self.server_kwargs)

        ...

    def make_http_server(self, routes, server_kwargs):
        """
        Used to make the http server itself
 
        takes in the result of calling ``tornado_routes()`` and the result of ``setup()``
        """
        # Defaults to a HTTPSServer
        return HTTPServer(tornado.web.Application(self.tornado_routes(), **server_kwargs))

    def announce_start(self):
        """Called after the server has been created and just before it is started"""
        # Defaults to a simple log statement
        log.info(f"Hosting server at http://{self.host}:{self.port}")

This means if you have extra arguments to provide to the Application then you
can just return them from the setup function. For example if I wanted to setup
a cookie secret:

.. code-block:: python

  class MyServer(Server):
      async def setup(self, cookie_secret):
          return {"cookie_secret": cookie_secret}

  MyServer(asyncio.Future()).serve("0.0.0.0", 9001, "sup3rs3cr3t")
