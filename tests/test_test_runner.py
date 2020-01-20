# coding: spec

from whirlwind.request_handlers.command import WSHandler
from whirlwind.server import Server, wait_for_futures
from whirlwind import test_helpers as thp
from whirlwind.commander import Commander
from whirlwind.store import Store

import asyncio
import time

store = Store()


@store.command("blah")
class Blah(store.Command):
    async def execute(self):
        return {"hello": "there"}


@store.command("meh")
class Meh(store.Command):
    async def execute(self):
        return {"good": "bye"}


class Server(Server):
    async def setup(self, wsconnections, server_time):
        self.commander = Commander(store)
        self.server_time = server_time
        self.wsconnections = wsconnections

    def tornado_routes(self):
        return [
            (
                "/v1/ws",
                WSHandler,
                {
                    "commander": self.commander,
                    "server_time": self.server_time,
                    "wsconnections": self.wsconnections,
                },
            )
        ]


class ServerRunner(thp.ServerRunner):
    async def before_start(self):
        self.num_tests = 0

    async def after_close(self, typ, exc, tb):
        assert self.num_tests == 2


class Runner(thp.ModuleLevelServer):
    async def started_test(self):
        self.runner.num_tests += 1

    async def server_runner(self):
        self.final_future = asyncio.Future()

        server_time = time.time()
        wsconnections = {}

        server = ServerRunner(
            self.final_future,
            thp.free_port(),
            Server(self.final_future),
            None,
            wsconnections,
            server_time,
        )

        await server.start()

        async def closer():
            await wait_for_futures(wsconnections)
            await server.closer()

        return server, closer


test_server = Runner()

setUp = test_server.setUp
tearDown = test_server.tearDown

describe thp.AsyncTestCase, "The Test Runner":
    use_default_loop = True

    @test_server.test
    async it "works one", server:
        async with server.ws_stream(self) as stream:
            await stream.start("/v1", {"command": "blah"})
            await stream.check_reply({"hello": "there"})

    @test_server.test
    async it "works two", server:
        async with server.ws_stream(self) as stream:
            await stream.start("/v1", {"command": "meh"})
            await stream.check_reply({"good": "bye"})
