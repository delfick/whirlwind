from whirlwind.server import Server, wait_for_futures
from whirlwind import test_helpers as thp
from whirlwind.commander import Commander

import asyncio
import pytest
import time


@pytest.fixture(scope="session")
async def server_wrapper():
    return ServerWrapper


class Asserter:
    def assertEqual(s, a, b, msg=None):
        __tracebackhide__ = True
        if msg:
            assert a == b, msg
        else:
            assert a == b

    def assertIs(s, a, b, msg=None):
        __tracebackhide__ = True
        if msg:
            assert a is b, msg
        else:
            assert a is b


class Server(Server):
    async def setup(self, tornado_routes, store, wsconnections, server_time):
        self.commander = Commander(store)
        self.server_time = server_time
        self.wsconnections = wsconnections
        self._tornado_routes = tornado_routes

    def tornado_routes(self):
        return self._tornado_routes(self)


class ServerRunner(thp.ServerRunner):
    async def before_start(self):
        self.num_tests = 0


class ServerWrapper:
    def __init__(self, store, tornado_routes):
        final_future = asyncio.Future()

        self.wsconnections = {}
        server_time = time.time()

        self.runner = ServerRunner(
            final_future,
            thp.free_port(),
            Server(final_future),
            None,
            tornado_routes,
            store,
            self.wsconnections,
            server_time,
        )

    async def __aenter__(self):
        await self.runner.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await wait_for_futures(self.wsconnections)
        _, nd = await asyncio.wait([self.runner.close(None, None, None)])

        if nd:
            assert False, "Failed to shutdown the runner"

    def test_wrap(self):
        class Wrap:
            async def __aenter__(s):
                self.runner.num_tests += 1

            async def __aexit__(s, exc_typ, exc, tb):
                pass

        return Wrap()

    def ws_stream(self):
        return thp.WSStream(self.runner, Asserter())
