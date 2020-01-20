# coding: spec

from whirlwind.request_handlers.command import WSHandler, CommandHandler
from whirlwind.server import Server, wait_for_futures
from whirlwind.request_handlers.base import reprer
from whirlwind import test_helpers as thp
from whirlwind.commander import Command
from whirlwind.store import NoSuchPath

from functools import partial
from unittest import mock
import asynctest
import asyncio
import time


class Thing:
    def __special_repr__(self):
        return {"special": "<|<THING>|>"}


def better_reprer(o):
    if isinstance(o, Thing):
        return o.__special_repr__()
    return reprer(o)


class Runner(thp.ServerRunner):
    def __init__(self, commander):
        self.final_future = asyncio.Future()
        self.wsconnections = {}

        class WSH(WSHandler):
            def initialize(self, *args, **kwargs):
                super().initialize(*args, **kwargs)
                self.reprer = better_reprer

        class CommandH(CommandHandler):
            def initialize(self, *args, **kwargs):
                super().initialize(*args, **kwargs)
                self.reprer = better_reprer

        class S(Server):
            def tornado_routes(s):
                return [
                    (
                        "/v1/ws",
                        WSH,
                        {
                            "commander": commander,
                            "server_time": time.time(),
                            "wsconnections": self.wsconnections,
                        },
                    ),
                    ("/v1/somewhere", CommandH, {"commander": commander}),
                    ("/v1/other", CommandH, {"commander": commander}),
                ]

        self.server = S(self.final_future)
        super().__init__(self.final_future, thp.free_port(), self.server, None)

    async def after_close(self, exc_type, exc, tb):
        await wait_for_futures(self.wsconnections)


describe thp.AsyncTestCase, "WSHandler and CommandHandler":

    def make_commander(self, handlerKls):
        commander = mock.Mock(name="commander")

        class Executor:
            def __init__(s, progress_cb, request_handler, **extra):
                s.extra = extra
                s.progress_cb = progress_cb
                s.request_handler = request_handler

            async def execute(s, path, body, extra_options=None):
                assert isinstance(s.request_handler, handlerKls)
                s.progress_cb("information", one=1, thing=Thing())
                s.progress_cb(ValueError("NOPE"))
                return {"success": True, "thing": Thing(), **s.extra}

        commander.executor.side_effect = Executor
        return commander

    @thp.with_timeout
    async it "WSHandler calls out to commander.execute":
        commander = self.make_commander(WSHandler)

        message_id = None

        async with Runner(commander) as server:
            async with server.ws_stream(self) as stream:
                await stream.start("/v1/somewhere", {"command": "one"})
                message_id = stream.message_id
                await stream.check_reply(
                    {
                        "progress": {
                            "info": "information",
                            "one": 1,
                            "thing": {"special": "<|<THING>|>"},
                        }
                    }
                )
                await stream.check_reply(
                    {"progress": {"error": "NOPE", "error_code": "ValueError"}}
                )
                await stream.check_reply(
                    {
                        "success": True,
                        "thing": {"special": "<|<THING>|>"},
                        "message_id": message_id,
                        "message_key": mock.ANY,
                    }
                )

    @thp.with_timeout
    async it "CommandHandler calls out to commander.execute":
        commander = self.make_commander(CommandHandler)

        async with Runner(commander) as server:
            await server.assertPUT(
                self,
                "/v1/somewhere",
                {"command": "one"},
                json_output={"success": True, "thing": {"special": "<|<THING>|>"}},
            )

    @thp.with_timeout
    async it "raises 404 if the path is invalid":
        commander = self.make_commander(CommandHandler)
        executor = mock.Mock(name="executor")
        executor.execute = asynctest.mock.CoroutineMock(name="execute")
        executor.execute.side_effect = NoSuchPath(wanted="/v1/other", available=["/v1/somewhere"])
        commander.executor = mock.Mock(name="executor()", return_value=executor)

        async with Runner(commander) as server:
            await server.assertPUT(
                self,
                "/v1/other",
                {"command": "one"},
                status=404,
                json_output={
                    "status": 404,
                    "error": "Specified path is invalid",
                    "wanted": "/v1/other",
                    "available": ["/v1/somewhere"],
                },
            )

            async with server.ws_stream(self) as stream:
                await stream.start("/v1/other", {"command": "one"})
                await stream.check_reply(
                    {
                        "status": 404,
                        "error": "Specified path is invalid",
                        "wanted": "/v1/other",
                        "available": ["/v1/somewhere"],
                    }
                )
