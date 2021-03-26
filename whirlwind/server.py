from tornado.httpserver import HTTPServer
import tornado.web
import logging

log = logging.getLogger("whirlwind.server")


class ForcedQuit(Exception):
    pass


class Server(object):
    def __init__(self, final_future):
        self.final_future = final_future

    async def serve(self, host, port, *args, **kwargs):
        self.port = port
        self.host = host
        self.server_kwargs = await self.setup(*args, **kwargs)
        if self.server_kwargs is None:
            self.server_kwargs = {}

        self.routes = self.tornado_routes()
        self.http_server = self.make_http_server(self.routes, self.server_kwargs)
        self.announce_start()

        self.http_server.listen(self.port, self.host)
        try:
            await self.wait_for_end()
        except ForcedQuit:
            log.info("The server was told to shut down")
        finally:
            try:
                self.http_server.stop()
            finally:
                await self.cleanup()

    async def wait_for_end(self):
        """Hook that will end when we need to stop the server"""
        await self.final_future

    def make_http_server(self, routes, server_kwargs):
        """
        Used to make the http server itself

        We expect it at least has ``listen(port, host)`` and ``stop()``
        """
        return HTTPServer(tornado.web.Application(self.tornado_routes(), **server_kwargs))

    def announce_start(self):
        """Called after the server has been created and just before it is started"""
        log.info(f"Hosting server at http://{self.host}:{self.port}")

    async def setup(self, *args, **kwargs):
        """
        Hook that receives all extra args and kwargs from serve

        The return of this function is either None or a dictionary of kwargs
        to add to our instantiation of the tornado.web.Application.
        """

    def tornado_routes(self):
        """
        Must be implemented to provide the list of routes given to the tornado.web.Application
        """
        raise NotImplementedError()

    async def cleanup(self):
        """Called after the server has stopped"""
