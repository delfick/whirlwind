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
        await self.setup(*args, **kwargs)

        http_server = HTTPServer(tornado.web.Application(self.tornado_routes()))

        log.info(f"Hosting server at http://{host}:{port}")

        http_server.listen(port, host)
        try:
            await self.final_future
        except ForcedQuit:
            log.info("The server was told to shut down")
        finally:
            http_server.stop()

    async def setup(self, *args, **kwargs):
        pass

    def tornado_routes(self):
        raise NotImplementedError()
