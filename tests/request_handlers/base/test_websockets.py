# coding: spec

from whirlwind.request_handlers.base import SimpleWebSocketBase, Finished, MessageFromExc
from whirlwind import test_helpers as thp
from whirlwind.server import Server

from contextlib import contextmanager
from unittest import mock
import asynctest
import asyncio
import pytest
import socket
import types
import time
import uuid


@pytest.fixture()
def make_wrapper(server_wrapper):
    def make_wrapper(Handler):
        def tornado_routes(server):
            return [
                (
                    "/v1/ws",
                    Handler,
                    {"server_time": time.time(), "wsconnections": server.wsconnections},
                ),
                (
                    "/v1/ws_no_server_time",
                    Handler,
                    {"server_time": None, "wsconnections": server.wsconnections},
                ),
            ]

        return server_wrapper(None, tornado_routes)

    return make_wrapper


describe "SimpleWebSocketBase":

    @pytest.mark.async_timeout(200)
    async it "does not have server_time message if that is set to None", make_wrapper:

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                return "blah"

        message_id = str(uuid.uuid1())
        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect(
                skip_hook=True, path="/v1/ws_no_server_time"
            )
            await server.runner.ws_write(
                connection,
                {"path": "/one/two", "body": {"hello": "there"}, "message_id": message_id},
            )
            res = await server.runner.ws_read(connection)
            assert res == {"reply": "blah", "message_id": message_id}

            connection.close()
            assert await server.runner.ws_read(connection) is None

    async it "knows when the connection has closed", make_wrapper:
        done = asyncio.Future()

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                progress_cb(body)
                try:
                    await s.connection_future
                except asyncio.CancelledError:
                    done.set_result(True)

        message_id = str(uuid.uuid1())
        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect(
                skip_hook=True, path="/v1/ws_no_server_time"
            )
            await server.runner.ws_write(
                connection,
                {"path": "/one/two", "body": {"hello": "there"}, "message_id": message_id},
            )
            res = await server.runner.ws_read(connection)
            assert res == {"reply": {"progress": {"hello": "there"}}, "message_id": message_id}

            await asyncio.sleep(0.001)
            assert not done.done()

            connection.close()
            assert await server.runner.ws_read(connection) is None

        assert await done is True

    async it "can modify what comes from a progress message", make_wrapper:

        class Handler(SimpleWebSocketBase):
            def transform_progress(s, body, message, **kwargs):
                yield {"body": body, "message": message, "kwargs": kwargs}

            async def process_message(s, path, body, message_id, message_key, progress_cb):
                progress_cb("WAT", arg=1, do_log=False, stack_extra=1)
                return "blah"

        message_id = str(uuid.uuid1())
        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()
            msg = {"path": "/one/two", "body": {"hello": "there"}, "message_id": message_id}
            await server.runner.ws_write(connection, msg)

            res = await server.runner.ws_read(connection)
            progress = {
                "body": msg,
                "message": "WAT",
                "kwargs": {"arg": 1, "do_log": False, "stack_extra": 1},
            }
            assert res == {"reply": {"progress": progress}, "message_id": message_id}

            res = await server.runner.ws_read(connection)
            assert res == {"reply": "blah", "message_id": message_id}

            connection.close()
            assert await server.runner.ws_read(connection) is None

    async it "can yield 0 progress messages if we so desire", make_wrapper:

        class Handler(SimpleWebSocketBase):
            def transform_progress(s, body, message, **kwargs):
                if message == "ignore":
                    return
                yield message

            async def process_message(s, path, body, message_id, message_key, progress_cb):
                progress_cb("hello")
                progress_cb("ignore")
                progress_cb("there")
                return "blah"

        message_id = str(uuid.uuid1())
        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()
            msg = {"path": "/one/two", "body": {"hello": "there"}, "message_id": message_id}
            await server.runner.ws_write(connection, msg)

            async def assertProgress(expect):
                assert await server.runner.ws_read(connection) == {
                    "reply": {"progress": expect},
                    "message_id": message_id,
                }

            await assertProgress("hello")
            await assertProgress("there")

            res = await server.runner.ws_read(connection)
            assert res == {"reply": "blah", "message_id": message_id}

            connection.close()
            assert await server.runner.ws_read(connection) is None

    async it "can yield multiple progress messages if we so desire", make_wrapper:

        class Handler(SimpleWebSocketBase):
            def transform_progress(s, body, message, **kwargs):
                for m in message:
                    yield m

            async def process_message(s, path, body, message_id, message_key, progress_cb):
                progress_cb(["hello", "people"])
                return "blah"

        message_id = str(uuid.uuid1())
        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()
            msg = {"path": "/one/two", "body": {"hello": "there"}, "message_id": message_id}
            await server.runner.ws_write(connection, msg)

            async def assertProgress(expect):
                assert await server.runner.ws_read(connection) == {
                    "reply": {"progress": expect},
                    "message_id": message_id,
                }

            await assertProgress("hello")
            await assertProgress("people")

            res = await server.runner.ws_read(connection)
            assert res == {"reply": "blah", "message_id": message_id}

            connection.close()
            assert await server.runner.ws_read(connection) is None

    async it "calls the message_done callback", make_wrapper:
        info = {"message_key": None}
        called = []

        class Handler(SimpleWebSocketBase):
            def message_done(s, request, final, message_key, exc_info=None):
                called.append((request, final, message_key, exc_info))

            async def process_message(s, path, body, message_id, message_key, progress_cb):
                info["message_key"] = message_key
                called.append("process")
                progress_cb("hello")
                return "blah"

        message_id = str(uuid.uuid1())
        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()
            msg = {"path": "/one/two", "body": {"hello": "there"}, "message_id": message_id}
            await server.runner.ws_write(connection, msg)

            assert await server.runner.ws_read(connection) == {
                "reply": {"progress": "hello"},
                "message_id": message_id,
            }

            res = await server.runner.ws_read(connection)
            assert res == {"reply": "blah", "message_id": message_id}

            assert info["message_key"] is not None
            assert called == ["process", (msg, "blah", info["message_key"], None)]

            connection.close()
            assert await server.runner.ws_read(connection) is None

    async it "calls the message_done with exc_info if an exception is raised in process_message", make_wrapper:
        info = {"message_key": None}
        error = ValueError("NOPE")
        called = []

        class Handler(SimpleWebSocketBase):
            def message_done(s, request, final, message_key, exc_info=None):
                called.append((request, final, message_key, exc_info))

            async def process_message(s, path, body, message_id, message_key, progress_cb):
                info["message_key"] = message_key
                called.append("process")
                progress_cb("hello")
                raise error

        message_id = str(uuid.uuid1())
        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()
            msg = {"path": "/one/two", "body": {"hello": "there"}, "message_id": message_id}
            await server.runner.ws_write(connection, msg)

            assert await server.runner.ws_read(connection) == {
                "reply": {"progress": "hello"},
                "message_id": message_id,
            }

            res = await server.runner.ws_read(connection)
            reply = {
                "error": "Internal Server Error",
                "error_code": "InternalServerError",
                "status": 500,
            }
            assert res == {"reply": reply, "message_id": message_id}

            assert info["message_key"] is not None

            class ATraceback:
                def __eq__(s, other):
                    return isinstance(other, types.TracebackType)

            assert called == [
                "process",
                (msg, reply, info["message_key"], (ValueError, error, ATraceback())),
            ]

            connection.close()
            assert await server.runner.ws_read(connection) is None

    async it "message_done can be used to close the connection", make_wrapper:
        info = {"message_key": None}
        error = ValueError("NOPE")
        called = []

        class Handler(SimpleWebSocketBase):
            def message_done(s, request, final, message_key, exc_info=None):
                called.append((request, final, message_key, exc_info))
                s.close()

            async def process_message(s, path, body, message_id, message_key, progress_cb):
                info["message_key"] = message_key
                called.append("process")
                progress_cb("there")
                return {"one": "two"}

        message_id = str(uuid.uuid1())
        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()
            msg = {"path": "/one/two", "body": {"hello": "there"}, "message_id": message_id}
            await server.runner.ws_write(connection, msg)

            assert await server.runner.ws_read(connection) == {
                "reply": {"progress": "there"},
                "message_id": message_id,
            }

            res = await server.runner.ws_read(connection)
            assert res == {"reply": {"one": "two"}, "message_id": message_id}

            assert info["message_key"] is not None

            assert called == ["process", (msg, {"one": "two"}, info["message_key"], None)]

            assert await server.runner.ws_read(connection) is None

    async it "modifies ws_connection object", make_wrapper:

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                assert type(s.key) == str
                assert len(s.key) == 36
                assert message_id != message_key
                assert message_key != s.key
                assert message_key in s.wsconnections
                return "blah"

        message_id = str(uuid.uuid1())
        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()
            await server.runner.ws_write(
                connection,
                {"path": "/one/two", "body": {"hello": "there"}, "message_id": message_id},
            )
            res = await server.runner.ws_read(connection)
            assert server.wsconnections == {}

            connection.close()
            assert await server.runner.ws_read(connection) is None

    async it "waits for connections to close before ending server", make_wrapper:
        f1 = asyncio.Future()
        f2 = asyncio.Future()

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                f1.set_result(True)
                await asyncio.sleep(0.5)
                f2.set_result(True)
                return "blah"

        message_id = str(uuid.uuid1())
        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()
            await server.runner.ws_write(
                connection,
                {"path": "/one/two", "body": {"hello": "there"}, "message_id": message_id},
            )
            await f1
            assert len(server.wsconnections) == 1
            assert not f2.done()

        assert len(server.wsconnections) == 0
        assert f2.result() == True

    async it "can stay open", make_wrapper:
        message_info = {"keys": set(), "message_keys": []}

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                assert path == "/one/two"
                assert body == {"wat": mock.ANY}
                message_info["keys"].add(s.key)
                message_info["message_keys"].append(message_key)
                return body["wat"]

        message_id = str(uuid.uuid1())
        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()
            await server.runner.ws_write(
                connection, {"path": "/one/two", "body": {"wat": "one"}, "message_id": message_id},
            )
            res = await server.runner.ws_read(connection)
            assert res["message_id"] == message_id
            assert res["reply"] == "one"

            await server.runner.ws_write(
                connection, {"path": "/one/two", "body": {"wat": "two"}, "message_id": message_id},
            )
            res = await server.runner.ws_read(connection)
            assert res["message_id"] == message_id
            assert res["reply"] == "two"

            connection.close()
            assert await server.runner.ws_read(connection) is None

        assert len(message_info["keys"]) == 1
        assert len(message_info["message_keys"]) == len(set(message_info["message_keys"]))

    async it "can handle ticks for me", make_wrapper:

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                assert path == "/one/two"
                assert body == {"wat": mock.ANY}
                return body["wat"]

        message_id = str(uuid.uuid1())

        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()
            await server.runner.ws_write(connection, {"path": "__tick__", "message_id": "__tick__"})
            res = await server.runner.ws_read(connection)
            assert res["message_id"] == "__tick__"
            assert res["reply"] == {"ok": "thankyou"}

            await server.runner.ws_write(
                connection, {"path": "/one/two", "body": {"wat": "two"}, "message_id": message_id},
            )
            res = await server.runner.ws_read(connection)
            assert res["message_id"] == message_id
            assert res["reply"] == "two"

            connection.close()
            assert await server.runner.ws_read(connection) is None

    async it "complains if the message is incorrect", make_wrapper:

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                return "processed"

        invalid = [
            {"message_id": "just_message_id"},
            {"message_id": "no_path", "body": {}},
            {"path": "/no/message_id", "body": {}},
            {"path": "/no/body", "message_id": "blah"},
            {},
            "",
            "asdf",
            False,
            True,
            0,
            1,
            [],
            [1],
        ]

        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()

            for body in invalid:
                await server.runner.ws_write(connection, body)
                res = await server.runner.ws_read(connection)
                assert res is not None, "Got no reply to : '{}'".format(body)
                assert res["message_id"] == None
                assert "reply" in res
                assert "error" in res["reply"]

            connection.close()
            assert await server.runner.ws_read(connection) is None

    async it "can do multiple messages at the same time", make_wrapper:

        class Handler(SimpleWebSocketBase):
            do_close = False

            async def process_message(s, path, body, message_id, message_key, progress_cb):
                progress_cb({body["serial"]: ["info", "start"]})
                await asyncio.sleep(body["sleep"])
                return {"processed": body["serial"]}

        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()

            msg_id1 = str(uuid.uuid1())
            msg_id2 = str(uuid.uuid1())

            await server.runner.ws_write(
                connection,
                {"path": "/process", "body": {"serial": "1", "sleep": 0.1}, "message_id": msg_id1,},
            )
            await server.runner.ws_write(
                connection,
                {
                    "path": "/process",
                    "body": {"serial": "2", "sleep": 0.05},
                    "message_id": msg_id2,
                },
            )

            assert await server.runner.ws_read(connection) == {
                "message_id": msg_id1,
                "reply": {"progress": {"1": ["info", "start"]}},
            }
            assert await server.runner.ws_read(connection) == {
                "message_id": msg_id2,
                "reply": {"progress": {"2": ["info", "start"]}},
            }
            assert await server.runner.ws_read(connection) == {
                "message_id": msg_id2,
                "reply": {"processed": "2"},
            }
            assert await server.runner.ws_read(connection) == {
                "message_id": msg_id1,
                "reply": {"processed": "1"},
            }

            connection.close()
            assert await server.runner.ws_read(connection) is None

    async it "can close the websocket if we return self.Closing", make_wrapper:

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                if body["close"]:
                    return s.Closing
                else:
                    return "stillalive"

        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()

            msg_id = str(uuid.uuid1())
            await server.runner.ws_write(
                connection, {"path": "/process", "body": {"close": False}, "message_id": msg_id}
            )
            assert await server.runner.ws_read(connection) == {
                "message_id": msg_id,
                "reply": "stillalive",
            }

            msg_id = str(uuid.uuid1())
            await server.runner.ws_write(
                connection, {"path": "/process", "body": {"close": False}, "message_id": msg_id}
            )
            assert await server.runner.ws_read(connection) == {
                "message_id": msg_id,
                "reply": "stillalive",
            }

            msg_id = str(uuid.uuid1())
            await server.runner.ws_write(
                connection, {"path": "/process", "body": {"close": True}, "message_id": msg_id}
            )
            assert await server.runner.ws_read(connection) == {
                "message_id": msg_id,
                "reply": {"closing": "goodbye"},
            }

            assert await server.runner.ws_read(connection) is None

    async it "can handle arbitrary json for the body", make_wrapper:

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                return body

        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()

            msg_id = str(uuid.uuid1())
            body = {
                "one": "two",
                "three": 4,
                "five": ["six", "seven", []],
                "six": [],
                "seven": True,
                "eight": False,
                "nine": {"one": "two", "three": None, "four": {"five": "six"}},
            }

            await server.runner.ws_write(
                connection, {"path": "/process", "body": body, "message_id": msg_id}
            )
            assert await server.runner.ws_read(connection) == {"message_id": msg_id, "reply": body}
            connection.close()

            assert await server.runner.ws_read(connection) is None

    async it "can handle exceptions in process_message", make_wrapper:

        class BadError(Exception):
            def as_dict(ss):
                return {"error": str(ss)}

        errors = {"one": ValueError("lolz"), "two": BadError("Try again")}

        class Handler(SimpleWebSocketBase):
            def initialize(ss, *args, **kwargs):
                super().initialize(*args, **kwargs)

                def message_from_exc(exc_type, exc, tb):
                    if hasattr(exc, "as_dict"):
                        return {"error_code": exc_type.__name__, "error": exc.as_dict()}
                    else:
                        return MessageFromExc()(exc_type, exc, tb)

                ss.message_from_exc = message_from_exc

            async def process_message(s, path, body, message_id, message_key, progress_cb):
                raise errors[body["error"]]

        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()

            msg_id = str(uuid.uuid1())
            await server.runner.ws_write(
                connection, {"path": "/error", "body": {"error": "one"}, "message_id": msg_id}
            )
            assert await server.runner.ws_read(connection) == {
                "message_id": msg_id,
                "reply": {
                    "error": "Internal Server Error",
                    "error_code": "InternalServerError",
                    "status": 500,
                },
            }

            msg_id2 = str(uuid.uuid1())
            await server.runner.ws_write(
                connection, {"path": "/error", "body": {"error": "two"}, "message_id": msg_id2}
            )
            assert await server.runner.ws_read(connection) == {
                "message_id": msg_id2,
                "reply": {"error": {"error": "Try again"}, "error_code": "BadError"},
            }

            connection.close()
            assert await server.runner.ws_read(connection) is None

    async it "can handle a return that has as_dict on it", make_wrapper:

        class Ret:
            def __init__(s, value):
                s.value = value

            def as_dict(s):
                return {"result": "", "value": s.value}

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                return Ret("blah and stuff")

        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()

            msg_id = str(uuid.uuid1())
            await server.runner.ws_write(
                connection, {"path": "/thing", "body": {}, "message_id": msg_id}
            )
            assert await server.runner.ws_read(connection) == {
                "message_id": msg_id,
                "reply": {"result": "", "value": "blah and stuff"},
            }

            connection.close()
            assert await server.runner.ws_read(connection) is None

    async it "can process replies", make_wrapper:
        replies = []

        error1 = ValueError("Bad things happen")
        error2 = Finished(status=400, error="Stuff")

        class Handler(SimpleWebSocketBase):
            def process_reply(s, msg, exc_info=None):
                replies.append((msg, exc_info))

            async def process_message(s, path, body, message_id, message_key, progress_cb):
                if path == "/no_error":
                    return {"success": True}
                elif path == "/internal_error":
                    raise error1
                elif path == "/custom_return":
                    s.reply({"progress": {"error": "progress"}}, message_id=message_id)

                    class Ret:
                        def as_dict(s):
                            return MessageFromExc()(type(error2), error2, None)

                        @property
                        def exc_info(s):
                            return (type(error2), error2, None)

                    return Ret()

        async with make_wrapper(Handler) as server:
            connection = await server.runner.ws_connect()

            ##################
            ### NO_ERROR

            msg_id = str(uuid.uuid1())
            await server.runner.ws_write(
                connection, {"path": "/no_error", "body": {}, "message_id": msg_id}
            )
            assert await server.runner.ws_read(connection) == {
                "message_id": msg_id,
                "reply": {"success": True},
            }

            ##################
            ### INTERNAL_ERROR

            msg_id = str(uuid.uuid1())
            await server.runner.ws_write(
                connection, {"path": "/internal_error", "body": {}, "message_id": msg_id}
            )
            assert await server.runner.ws_read(connection) == {
                "message_id": msg_id,
                "reply": {
                    "error": "Internal Server Error",
                    "error_code": "InternalServerError",
                    "status": 500,
                },
            }

            ##################
            ### CUSTOM RETURN

            msg_id = str(uuid.uuid1())
            await server.runner.ws_write(
                connection, {"path": "/custom_return", "body": {}, "message_id": msg_id}
            )
            assert await server.runner.ws_read(connection) == {
                "message_id": msg_id,
                "reply": {"progress": {"error": "progress"}},
            }
            assert await server.runner.ws_read(connection) == {
                "message_id": msg_id,
                "reply": {"error": "Stuff", "status": 400},
            }

        class ATraceback:
            def __eq__(s, other):
                return isinstance(other, types.TracebackType)

        assert replies == [
            ({"success": True}, None),
            (
                {
                    "status": 500,
                    "error": "Internal Server Error",
                    "error_code": "InternalServerError",
                },
                (ValueError, error1, ATraceback()),
            ),
            ({"progress": {"error": "progress"}}, None),
            ({"error": "Stuff", "status": 400}, (Finished, error2, None)),
        ]
