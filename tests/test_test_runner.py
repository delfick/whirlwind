# coding: spec

from whirlwind.request_handlers.command import WSHandler
from whirlwind.server import Server, wait_for_futures
from whirlwind import test_helpers as thp
from whirlwind.commander import Commander
from whirlwind.store import Store

import asyncio
import pytest
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


def tornado_routes(server):
    return [
        (
            "/v1/ws",
            WSHandler,
            {
                "commander": server.commander,
                "server_time": server.server_time,
                "wsconnections": server.wsconnections,
            },
        )
    ]


describe "The Test Runner":

    @pytest.fixture(scope="class")
    async def runner(self, server_wrapper):
        async with server_wrapper(store, tornado_routes) as wrapper:
            yield wrapper
        assert wrapper.runner.num_tests == 2

    @pytest.fixture(autouse=True)
    async def per_test(self, runner):
        async with runner.test_wrap():
            yield

    async it "works one", runner:
        async with runner.ws_stream() as stream:
            await stream.start("/v1", {"command": "blah"})
            await stream.check_reply({"hello": "there"})

    async it "works two", runner:
        async with runner.ws_stream() as stream:
            await stream.start("/v1", {"command": "meh"})
            await stream.check_reply({"good": "bye"})
