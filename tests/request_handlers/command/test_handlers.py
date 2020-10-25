# coding: spec

from whirlwind.request_handlers.command import WSHandler, CommandHandler
from whirlwind.request_handlers.base import reprer
from whirlwind.store import NoSuchPath

from unittest import mock
import asyncio
import pytest
import time


class Thing:
    def __special_repr__(self):
        return {"special": "<|<THING>|>"}


def better_reprer(o):
    if isinstance(o, Thing):
        return o.__special_repr__()
    return reprer(o)


@pytest.fixture()
def final_future():
    fut = asyncio.Future()
    try:
        yield fut
    finally:
        fut.cancel()


@pytest.fixture()
def make_wrapper(server_wrapper, final_future):
    def make_wrapper(commander):
        class WSH(WSHandler):
            def initialize(s, *args, **kwargs):
                super().initialize(*args, **kwargs)
                s.reprer = better_reprer

        class CommandH(CommandHandler):
            def initialize(s, *args, **kwargs):
                super().initialize(*args, **kwargs)
                s.reprer = better_reprer

        def tornado_routes(server):
            return [
                (
                    "/v1/ws",
                    WSH,
                    {
                        "commander": commander,
                        "server_time": time.time(),
                        "final_future": final_future,
                        "wsconnections": server.wsconnections,
                    },
                ),
                ("/v1/somewhere", CommandH, {"commander": commander}),
                ("/v1/other", CommandH, {"commander": commander}),
            ]

        return server_wrapper(None, tornado_routes)

    return make_wrapper


describe "WSHandler and CommandHandler":

    def make_commander(self, handlerKls, *, do_allow_ws_only):
        commander = mock.Mock(name="commander")

        class Executor:
            def __init__(s, progress_cb, request_handler, **extra):
                s.extra = extra
                s.progress_cb = progress_cb
                s.request_handler = request_handler

            async def execute(
                s, path, body, extra_options=None, allow_ws_only=False, request_future=None
            ):
                assert allow_ws_only == do_allow_ws_only
                assert isinstance(s.request_handler, handlerKls)
                s.progress_cb("information", one=1, thing=Thing())
                s.progress_cb(ValueError("NOPE"))
                return {"success": True, "thing": Thing(), **s.extra}

        commander.executor.side_effect = Executor
        return commander

    async it "WSHandler calls out to commander.execute", make_wrapper:
        commander = self.make_commander(WSHandler, do_allow_ws_only=True)

        message_id = None

        async with make_wrapper(commander) as server:
            async with server.ws_stream() as stream:
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

    async it "CommandHandler calls out to commander.execute", make_wrapper:
        commander = self.make_commander(CommandHandler, do_allow_ws_only=False)

        async with make_wrapper(commander) as server:
            await server.assertHTTP(
                "PUT",
                "/v1/somewhere",
                {"json": {"command": "one"}},
                json_output={"success": True, "thing": {"special": "<|<THING>|>"}},
            )

    async it "raises 404 if the path is invalid", make_wrapper:
        commander = self.make_commander(CommandHandler, do_allow_ws_only=False)
        executor = mock.Mock(name="executor")
        executor.execute = pytest.helpers.AsyncMock(name="execute")
        executor.execute.side_effect = NoSuchPath(wanted="/v1/other", available=["/v1/somewhere"])
        commander.executor = mock.Mock(name="executor()", return_value=executor)

        async with make_wrapper(commander) as server:
            await server.assertHTTP(
                "PUT",
                "/v1/other",
                {"json": {"command": "one"}},
                status=404,
                json_output={
                    "status": 404,
                    "error": "Specified path is invalid",
                    "wanted": "/v1/other",
                    "available": ["/v1/somewhere"],
                },
            )

            async with server.ws_stream() as stream:
                await stream.start("/v1/other", {"command": "one"})
                await stream.check_reply(
                    {
                        "status": 404,
                        "error": "Specified path is invalid",
                        "wanted": "/v1/other",
                        "available": ["/v1/somewhere"],
                    }
                )
