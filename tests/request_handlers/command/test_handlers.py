# coding: spec

from whirlwind.request_handlers.command import WSHandler, CommandHandler
from whirlwind.server import Server, wait_for_futures
from whirlwind import test_helpers as thp
from whirlwind.commander import Command

from functools import partial
from unittest import mock
import asynctest
import asyncio
import time

class Runner(thp.ServerRunner):
    def __init__(self, commander):
        self.final_future = asyncio.Future()
        self.wsconnections = {}

        class S(Server):
            def tornado_routes(s):
                return [
                      ( "/v1/ws"
                      , WSHandler
                      , { "commander": commander
                        , "server_time": time.time()
                        , "wsconnections": self.wsconnections
                        }
                      )
                    , ( "/v1/somewhere"
                      , CommandHandler
                      , {"commander": commander}
                      )
                    ]

        self.server = S(self.final_future)
        super().__init__(self.final_future, thp.free_port(), self.server, None)

    async def after_close(self):
        await wait_for_futures(self.wsconnections)

describe thp.AsyncTestCase, "WSHandler and CommandHandler":
    def make_commander(self, handlerKls):
        commander = mock.Mock(name="commander")

        def execute(path, body, progress_cb, request_handler):
            self.assertIsInstance(request_handler, handlerKls)
            progress_cb("information", one=1)
            progress_cb(ValueError("NOPE"))
            return {"success": True}
        commander.execute = asynctest.mock.CoroutineMock(name="execute", side_effect=execute)
        return commander

    @thp.with_timeout
    async it "WSHandler calls out to commander.execute":
        commander = self.make_commander(WSHandler)

        async with Runner(commander) as server:
            async with server.ws_stream(self) as stream:
                await stream.start("/v1/somewhere", {"command": "one"})
                await stream.check_reply({'progress': {'info': "information", "one": 1}})
                await stream.check_reply({'progress': {'error': "NOPE", "error_code": "ValueError"}})
                await stream.check_reply({"success": True})

        commander.execute.assert_called_once_with("/v1/somewhere", {"command": "one"}, mock.ANY, mock.ANY)

    @thp.with_timeout
    async it "CommandHandler calls out to commander.execute":
        commander = self.make_commander(CommandHandler)

        async with Runner(commander) as server:
            await server.assertPUT(self, "/v1/somewhere", {"command": "one"}, json_output={"success": True})

        commander.execute.assert_called_once_with("/v1/somewhere", {"command": "one"}, mock.ANY, mock.ANY)
