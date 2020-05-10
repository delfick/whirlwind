# coding: spec

from whirlwind.request_handlers.base import MessageFromExc
from whirlwind.request_handlers.command import WSHandler
from whirlwind.commander import Commander
from whirlwind.store import Store

from delfick_project.option_merge.formatter import MergedOptionStringFormatter
from delfick_project.errors import DelfickError
from delfick_project.norms import dictobj, sb
from unittest import mock
import asyncio
import pytest
import time
import uuid


store = Store(formatter=MergedOptionStringFormatter)


@store.command("interactive")
class Interactive(store.Command):
    progress_cb = store.injected("progress_cb")

    async def execute(self, messages):
        self.progress_cb("started")
        async for message in messages:
            message.no_process()
            if isinstance(message.command, Stop):
                break


@store.command("stop", parent=Interactive)
class Stop(store.Command):
    pass


@store.command("processing")
class Processing(store.Command):
    handler = store.injected("request_handler")
    progress_cb = store.injected("progress_cb")

    async def execute(self, messages):
        self.progress_cb("started")
        async for message in messages:
            assert message.command.handler is self.handler
            await message.process()


@store.command("a_command", parent=Processing)
class Acommand(store.Command):
    handler = store.injected("request_handler")

    async def execute(self):
        return "boring"


@store.command("cancel_connection_fut", parent=Processing)
class CancelConnectionFut(store.Command):
    handler = store.injected("request_handler")

    async def execute(self):
        self.handler.connection_future.cancel()
        return "cancelled"


@store.command("interactive_with_error_receiving")
class InteractiveWithErrorRecieving(store.Command):
    progress_cb = store.injected("progress_cb")

    async def execute(self, messages):
        self.progress_cb("started")
        async for _, message in messages:
            message.no_process()


@store.command("stop", parent=InteractiveWithErrorRecieving)
class Stop2(store.Command):
    pass


@store.command("interactive_with_error_after_receive")
class InteractiveWithErrorAfterReceive(store.Command):
    progress_cb = store.injected("progress_cb")

    async def execute(self, messages):
        self.progress_cb("started")
        async for message in messages:
            raise DelfickError("NUP", fail=True)
            message.no_process()


@store.command("stop", parent=InteractiveWithErrorAfterReceive)
class Stop3(store.Command):
    pass


@store.command("interactive_with_error_after_process")
class InteractiveWithErrorAfterProcess(store.Command):
    progress_cb = store.injected("progress_cb")

    async def execute(self, messages):
        self.progress_cb("started")
        async for message in messages:
            self.progress_cb(await message.process())
            raise DelfickError("NUP", fail=True)


class Echo(store.Command):
    wrap = None
    info = dictobj.Field(sb.dictionary_spec)

    async def execute(self):
        if "error" in self.info:
            raise Exception(self.info["error"])

        if self.wrap:
            return {self.wrap: self.info}
        else:
            return self.info


@store.command("echo", parent=InteractiveWithErrorAfterProcess)
class Echo1(Echo):
    wrap = "done_good"


@store.command("interactive_with_sub_interactive")
class InteractiveWithSubInteractive(store.Command):
    progress_cb = store.injected("progress_cb")

    async def execute(self, messages):
        self.progress_cb("started")
        async for message in messages:
            res = await message.process()
            self.progress_cb({message.command.__class__.__name__: res})
            if res == {"stop": True}:
                break


@store.command("echo", parent=InteractiveWithSubInteractive)
class Echo2(Echo):
    pass


@store.command("sub_interactive", parent=InteractiveWithSubInteractive)
class SubInteractive(store.Command):
    progress_cb = store.injected("progress_cb")

    wrap = dictobj.Field(sb.string_spec, wrapper=sb.required)

    async def execute(self, messages):
        self.progress_cb("started")
        async for message in messages:
            res = await message.process()
            self.progress_cb({self.wrap: res})
            if res == {"stop": True, "please": True}:
                break


@store.command("echo", parent=SubInteractive)
class Echo3(Echo):
    pass


class MessageFromExc(MessageFromExc):
    def process(self, exc_type, exc, tb):
        if hasattr(exc, "as_dict"):
            error = exc.as_dict()
        else:
            error = str(exc)
        return {"error_code": exc.__class__.__name__, "error": error}


class WSHandler(WSHandler):
    def initialize(self, *args, **kwargs):
        super().initialize(*args, **kwargs)
        self.message_from_exc = MessageFromExc()


@pytest.fixture()
def final_future():
    fut = asyncio.Future()
    try:
        yield fut
    finally:
        fut.cancel()


@pytest.fixture()
async def runner(server_wrapper, final_future):
    def tornado_routes(server):
        return [
            (
                "/v1/ws",
                WSHandler,
                {
                    "final_future": final_future,
                    "commander": Commander(store, final_future=server.final_future),
                    "server_time": time.time(),
                    "wsconnections": server.wsconnections,
                },
            ),
        ]

    async with server_wrapper(store, tornado_routes) as server:
        yield server.runner


describe "Interactive commands":

    async it "the parent is finished when it's connection future is finished", runner, asserter, final_future:
        async with runner.ws_stream(asserter) as stream:
            await stream.start("/v1", {"command": "processing"})
            message_id = stream.message_id
            await stream.check_reply({"progress": {"info": "started"}})

            child_message_id = str(uuid.uuid1())
            await stream.start(
                "/v1", {"command": "a_command"}, message_id=[message_id, child_message_id]
            )
            await stream.check_reply("boring", message_id=[message_id, child_message_id])

            child_message_id = str(uuid.uuid1())
            await stream.start(
                "/v1",
                {"command": "cancel_connection_fut"},
                message_id=[message_id, child_message_id],
            )
            await stream.check_reply("cancelled", message_id=[message_id, child_message_id])

    async it "it can start and control interactive commands", runner, asserter:
        async with runner.ws_stream(asserter) as stream:
            await stream.start("/v1", {"command": "interactive"})
            message_id = stream.message_id
            await stream.check_reply({"progress": {"info": "started"}})

            child_message_id = str(uuid.uuid1())
            await stream.start(
                "/v1", {"command": "stop"}, message_id=[message_id, child_message_id]
            )
            await stream.check_reply({"received": True}, message_id=[message_id, child_message_id])
            await stream.check_reply({"done": True})

    async it "can fail if we fail to read from messages properly", runner, asserter:
        async with runner.ws_stream(asserter) as stream:
            await stream.start("/v1", {"command": "interactive_with_error_receiving"})
            message_id = stream.message_id
            await stream.check_reply({"progress": {"info": "started"}})

            child_message_id = str(uuid.uuid1())
            await stream.start(
                "/v1", {"command": "stop"}, message_id=[message_id, child_message_id]
            )

            error = {"error_code": "TypeError", "error": mock.ANY}
            await stream.check_reply(error, message_id=[message_id, child_message_id])
            await stream.check_reply(error)

    async it "can fail if we fail to process a command", runner, asserter:
        async with runner.ws_stream(asserter) as stream:
            await stream.start("/v1", {"command": "interactive_with_error_after_receive"})
            message_id = stream.message_id
            await stream.check_reply({"progress": {"info": "started"}})

            child_message_id = str(uuid.uuid1())
            await stream.start(
                "/v1", {"command": "stop"}, message_id=[message_id, child_message_id]
            )

            error = {"error_code": "DelfickError", "error": {"message": "NUP", "fail": True}}
            await stream.check_reply(error, message_id=[message_id, child_message_id])
            await stream.check_reply(error)

    async it "can fail after we process a command", runner, asserter:
        async with runner.ws_stream(asserter) as stream:
            await stream.start("/v1", {"command": "interactive_with_error_after_process"})
            message_id = stream.message_id
            await stream.check_reply({"progress": {"info": "started"}})

            child_message_id = str(uuid.uuid1())
            await stream.start(
                "/v1",
                {"command": "echo", "args": {"info": {"amaze": True}}},
                message_id=[message_id, child_message_id],
            )

            await stream.check_reply(
                {"done_good": {"amaze": True}}, message_id=[message_id, child_message_id]
            )
            await stream.check_reply({"progress": {"done_good": {"amaze": True}}})

            error = {"error_code": "DelfickError", "error": {"message": "NUP", "fail": True}}
            await stream.check_reply(error)

    async it "can have sub interactives", runner, asserter:
        async with runner.ws_stream(asserter) as stream:
            await stream.start("/v1", {"command": "interactive_with_sub_interactive"})
            message_id = stream.message_id
            await stream.check_reply({"progress": {"info": "started"}})

            child_message_id = str(uuid.uuid1())
            await stream.start(
                "/v1",
                {"command": "echo", "args": {"info": {"hello": "there"}}},
                message_id=[message_id, child_message_id],
            )

            await stream.check_reply({"hello": "there"}, message_id=[message_id, child_message_id])
            await stream.check_reply({"progress": {"Echo2": {"hello": "there"}}})

            sub_message_id = str(uuid.uuid1())
            await stream.start(
                "/v1",
                {"command": "sub_interactive", "args": {"wrap": "sub"}},
                message_id=[message_id, sub_message_id],
            )
            await stream.check_reply(
                {"progress": {"info": "started"}}, message_id=[message_id, sub_message_id],
            )

            sub_child_message_id = str(uuid.uuid1())
            await stream.start(
                "/v1",
                {"command": "echo", "args": {"info": {"child1": True}}},
                message_id=[message_id, sub_message_id, sub_child_message_id],
            )

            await stream.check_reply(
                {"child1": True}, message_id=[message_id, sub_message_id, sub_child_message_id],
            )
            await stream.check_reply(
                {"progress": {"sub": {"child1": True}}}, message_id=[message_id, sub_message_id]
            )

            sub_child_message_id = str(uuid.uuid1())
            await stream.start(
                "/v1",
                {"command": "echo", "args": {"info": {"stop": True}}},
                message_id=[message_id, sub_message_id, sub_child_message_id],
            )

            await stream.check_reply(
                {"stop": True}, message_id=[message_id, sub_message_id, sub_child_message_id],
            )
            await stream.check_reply(
                {"progress": {"sub": {"stop": True}}}, message_id=[message_id, sub_message_id]
            )

            sub_child_message_id = str(uuid.uuid1())
            await stream.start(
                "/v1",
                {"command": "echo", "args": {"info": {"stop": True, "please": True}}},
                message_id=[message_id, sub_message_id, sub_child_message_id],
            )

            await stream.check_reply(
                {"stop": True, "please": True},
                message_id=[message_id, sub_message_id, sub_child_message_id],
            )
            await stream.check_reply(
                {"progress": {"sub": {"stop": True, "please": True}}},
                message_id=[message_id, sub_message_id],
            )
            await stream.check_reply({"done": True}, message_id=[message_id, sub_message_id])
            await stream.check_reply({"progress": {"SubInteractive": None}})

            child_message_id = str(uuid.uuid1())
            await stream.start(
                "/v1",
                {"command": "echo", "args": {"info": {"hi": "again"}}},
                message_id=[message_id, child_message_id],
            )

            await stream.check_reply({"hi": "again"}, message_id=[message_id, child_message_id])
            await stream.check_reply({"progress": {"Echo2": {"hi": "again"}}})

            child_message_id = str(uuid.uuid1())
            await stream.start(
                "/v1",
                {"command": "echo", "args": {"info": {"stop": True}}},
                message_id=[message_id, child_message_id],
            )

            await stream.check_reply({"stop": True}, message_id=[message_id, child_message_id])
            await stream.check_reply({"progress": {"Echo2": {"stop": True}}})
            await stream.check_reply({"done": True})

    async it "exceptions from processing a command rise", runner, asserter, final_future:
        async with runner.ws_stream(asserter) as stream:
            await stream.start("/v1", {"command": "interactive_with_sub_interactive"})
            message_id = stream.message_id
            await stream.check_reply({"progress": {"info": "started"}})

            child_message_id = str(uuid.uuid1())
            await stream.start(
                "/v1",
                {"command": "echo", "args": {"info": {"error": "SAD"}}},
                message_id=[message_id, child_message_id],
            )

            await stream.check_reply(
                {"error_code": "Exception", "error": "SAD"},
                message_id=[message_id, child_message_id],
            )
            await stream.check_reply({"error_code": "Exception", "error": "SAD"})
