# coding: spec

from whirlwind.server import wait_for_futures, Server
from whirlwind import test_helpers as thp

from unittest import mock
import asynctest
import asyncio

describe thp.AsyncTestCase, "wait_for_futures":
    @thp.with_timeout
    async it "waits on not done future and ignores failures":
        pending_fut1 = asyncio.Future()
        asyncio.get_event_loop().call_later(0.1, pending_fut1.set_result, True)

        pending_fut2 = asyncio.Future()
        asyncio.get_event_loop().call_later(0.2, pending_fut2.set_exception, TypeError("asdf"))

        pending_fut3 = asyncio.Future()
        asyncio.get_event_loop().call_later(0.2, pending_fut3.cancel)

        done_fut1 = asyncio.Future()
        done_fut1.set_result(False)

        done_fut2 = asyncio.Future()
        done_fut2.cancel()

        done_fut3 = asyncio.Future()
        done_fut3.set_exception(ValueError("NAH"))

        futures = {
              1: pending_fut1, 2: pending_fut2, 3: pending_fut3
            , 4: done_fut1, 5: done_fut2, 6: done_fut3
            }

        await wait_for_futures(futures)
        assert True, "Successfully waited!"

        for fut in futures.values():
            assert fut.done()

describe thp.AsyncTestCase, "setup":
    class assertSetupWorks:
        def __init__(self, test, setup_return, *args, **kwargs):
            self.args = args
            self.test = test
            self.kwargs = kwargs

            self.port = mock.Mock(name="port")
            self.host = mock.Mock(name="host")
            self.routes = mock.Mock(name="routes")

            self.http_server = mock.Mock(name="http_server")
            self.application = mock.Mock(name='application')

            self.FakeHTTPServer = mock.Mock(name="HTTPServer", return_value=self.http_server)
            self.FakeApplication = mock.Mock(name="Application", return_value=self.application)

            self.setup = asynctest.mock.CoroutineMock(name="setup", return_value=setup_return)
            self.cleanup = asynctest.mock.CoroutineMock(name="cleanup")
            self.tornado_routes = mock.Mock(name="tornado_routes", return_value=self.routes)

            self.patchHTTPServer = mock.patch("whirlwind.server.HTTPServer", self.FakeHTTPServer)
            self.patchApplication = mock.patch("tornado.web.Application", self.FakeApplication)

            self.patch_setup = mock.patch.object(Server, "setup", self.setup)
            self.patch_cleanup = mock.patch.object(Server, "cleanup", self.cleanup)
            self.patch_tornado_routes = mock.patch.object(Server, "tornado_routes", self.tornado_routes)

            self.final_future = asyncio.Future()

        async def __aenter__(self):
            self.patchHTTPServer.start()
            self.patchApplication.start()
            self.patch_setup.start()
            self.patch_cleanup.start()
            self.patch_tornado_routes.start()

            server = Server(self.final_future)
            t = thp.async_as_background(server.serve(self.host, self.port, *self.args, **self.kwargs))
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
                self.test.assertEqual(len(self.http_server.stop.mock_calls), 0)

                self.final_future.cancel()
                await asyncio.sleep(0.1)

                self.http_server.stop.assert_called_once_with()
                self.cleanup.assert_called_once_with()
            finally:
                self.patch_cleanup.stop()
                if not self.final_future.done():
                    self.final_future.cancel()

    @thp.with_timeout
    async it "takes in extra parameters and gives back to tornado.web.Application":
        a = mock.Mock(name="a")
        b = mock.Mock(name="b")
        setup_return = {"cookie_secret": "sup3rs3cr3t"}

        async with self.assertSetupWorks(self, setup_return, a, b=b) as (routes, setup, FakeApplication):
            setup.assert_called_once_with(a, b=b)
            FakeApplication.assert_called_once_with(routes, cookie_secret="sup3rs3cr3t")

    @thp.with_timeout
    async it "works if setup returns None":
        c = mock.Mock(name="c")
        d = mock.Mock(name="d")

        async with self.assertSetupWorks(self, None, c, d=d) as (routes, setup, FakeApplication):
            setup.assert_called_once_with(c, d=d)
            FakeApplication.assert_called_once_with(routes)
