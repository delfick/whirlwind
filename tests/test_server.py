# coding: spec

from whirlwind.server import Server

from unittest import mock
import asyncio
import pytest

describe "setup":

    class assertSetupWorks:
        def __init__(self, test, setup_return, *args, **kwargs):
            self.args = args
            self.test = test
            self.kwargs = kwargs

            self.port = mock.Mock(name="port")
            self.host = mock.Mock(name="host")
            self.routes = mock.Mock(name="routes")

            self.http_server = mock.Mock(name="http_server")
            self.application = mock.Mock(name="application")

            self.FakeHTTPServer = mock.Mock(name="HTTPServer", return_value=self.http_server)
            self.FakeApplication = mock.Mock(name="Application", return_value=self.application)

            self.setup = pytest.helpers.AsyncMock(name="setup", return_value=setup_return)
            self.cleanup = pytest.helpers.AsyncMock(name="cleanup")
            self.tornado_routes = mock.Mock(name="tornado_routes", return_value=self.routes)

            self.patchHTTPServer = mock.patch("whirlwind.server.HTTPServer", self.FakeHTTPServer)
            self.patchApplication = mock.patch("tornado.web.Application", self.FakeApplication)

            self.patch_setup = mock.patch.object(Server, "setup", self.setup)
            self.patch_cleanup = mock.patch.object(Server, "cleanup", self.cleanup)
            self.patch_tornado_routes = mock.patch.object(
                Server, "tornado_routes", self.tornado_routes
            )

            self.final_future = asyncio.Future()

        async def __aenter__(self):
            self.patchHTTPServer.start()
            self.patchApplication.start()
            self.patch_setup.start()
            self.patch_cleanup.start()
            self.patch_tornado_routes.start()

            server = Server(self.final_future)
            asyncio.get_event_loop().create_task(
                server.serve(self.host, self.port, *self.args, **self.kwargs)
            )
            await asyncio.sleep(0.1)

            return self.routes, self.setup, self.FakeApplication

        async def __aexit__(self, exc_typ, exc, tb):
            try:
                self.patchHTTPServer.stop()
                self.patchApplication.stop()
                self.patch_setup.stop()
                self.patch_tornado_routes.stop()

                self.FakeHTTPServer.assert_called_once_with(self.application)
                self.http_server.listen.assert_called_once_with(self.port, self.host)
                assert len(self.http_server.stop.mock_calls) == 0

                self.final_future.cancel()
                await asyncio.sleep(0.1)

                self.http_server.stop.assert_called_once_with()
                self.cleanup.assert_called_once_with()
            finally:
                self.patch_cleanup.stop()
                if not self.final_future.done():
                    self.final_future.cancel()

    async it "takes in extra parameters and gives back to tornado.web.Application":
        a = mock.Mock(name="a")
        b = mock.Mock(name="b")
        setup_return = {"cookie_secret": "sup3rs3cr3t"}

        async with self.assertSetupWorks(self, setup_return, a, b=b) as (
            routes,
            setup,
            FakeApplication,
        ):
            setup.assert_called_once_with(a, b=b)
            FakeApplication.assert_called_once_with(routes, cookie_secret="sup3rs3cr3t")

    async it "works if setup returns None":
        c = mock.Mock(name="c")
        d = mock.Mock(name="d")

        async with self.assertSetupWorks(self, None, c, d=d) as (routes, setup, FakeApplication):
            setup.assert_called_once_with(c, d=d)
            FakeApplication.assert_called_once_with(routes)
