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
        server_kwargs = await self.setup(*args, **kwargs)
        if server_kwargs is None:
            server_kwargs = {}

        http_server = HTTPServer(tornado.web.Application(self.tornado_routes(), **server_kwargs))

        log.info(f"Hosting server at http://{host}:{port}")

        http_server.listen(port, host)
        try:
            await self.final_future
        except ForcedQuit:
            log.info("The server was told to shut down")
        finally:
            try:
                http_server.stop()
            finally:
                await self.cleanup()

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

async def wait_for_futures(futures):
    """
    Helper for waiting on futures in a dictionary of {key: future}

    Useful for waiting on the wsconnections object given to a WSHandler
    """
    for t in list(futures.values()):
        if not t.done():
            try:
                await t
            except:
                pass
