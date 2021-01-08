# coding: spec

from whirlwind.request_handlers.base import SimpleWebSocketBase, Finished, MessageFromExc

from unittest import mock
import asyncio
import pytest
import types
import time
import uuid


@pytest.fixture()
def final_future():
    fut = asyncio.Future()
    try:
        yield fut
    finally:
        fut.cancel()


@pytest.fixture()
def make_server(server_wrapper, final_future):
    def make_server(Handler):
        def tornado_routes(server):
            return [
                (
                    "/v1/ws",
                    Handler,
                    {
                        "final_future": final_future,
                        "server_time": time.time(),
                        "wsconnections": server.wsconnections,
                    },
                ),
                (
                    "/v1/ws_no_server_time",
                    Handler,
                    {
                        "final_future": final_future,
                        "server_time": None,
                        "wsconnections": server.wsconnections,
                    },
                ),
            ]

        return server_wrapper(None, tornado_routes)

    return make_server


describe "SimpleWebSocketBase":

    async it "does not have server_time message if that is set to None", make_server:

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                return "blah"

        async with make_server(Handler) as server:
            async with server.ws_stream(
                path="/v1/ws_no_server_time", gives_server_time=False
            ) as stream:
                message_id = await stream.start("/one/two", {"hello": "there"})
                await stream.check_reply("blah", message_id=message_id)

    async it "has cancelled connection fut if final_future already done", make_server, final_future:
        called = []

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                assert s.connection_future.done()
                called.append("processed")
                return "blah"

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                final_future.cancel()
                message_id = await stream.start("/one/two", {"hello": "there"})
                await stream.check_reply("blah", message_id=message_id)

        assert called == ["processed"]

    async it "cancels connection fut if final_future gets fulfilled done", make_server, final_future:
        info = {}
        called = []

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                called.append("processing")
                await asyncio.wait([s.connection_future])
                called.append("processed")
                return info["value"]

        assert not final_future._callbacks

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                message_id = await stream.start("/one/two", {"hello": "there"})

                await asyncio.sleep(0.1)
                assert called == ["processing"]

                assert len(final_future._callbacks) == 1
                final_future.cancel()
                info["value"] = "VALUE"

                await stream.check_reply("VALUE", message_id=message_id)
                assert not final_future._callbacks

        assert called == ["processing", "processed"]

    async it "knows when the connection has closed", make_server:
        done = asyncio.Future()

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                progress_cb(body)
                try:
                    await s.connection_future
                except asyncio.CancelledError:
                    done.set_result(True)

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                message_id = await stream.start("/one/two", {"hello": "there"})
                await stream.check_reply({"progress": {"hello": "there"}}, message_id=message_id)

                await asyncio.sleep(0.001)
                assert not done.done()

        assert await done is True

    async it "can modify what comes from a progress message", make_server:

        class Handler(SimpleWebSocketBase):
            def transform_progress(s, body, message, **kwargs):
                yield {"progress": {"body": body, "message": message, "kwargs": kwargs}}

            async def process_message(s, path, body, message_id, message_key, progress_cb):
                progress_cb("WAT", arg=1, do_log=False, stack_extra=1)
                return "blah"

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                message_id = await stream.start("/one/two", {"hello": "there"})

                progress = {
                    "body": {
                        "path": "/one/two",
                        "body": {"hello": "there"},
                        "message_id": message_id,
                    },
                    "message": "WAT",
                    "kwargs": {"arg": 1, "do_log": False, "stack_extra": 1},
                }
                await stream.check_reply({"progress": progress}, message_id=message_id)
                await stream.check_reply("blah", message_id=message_id)

    async it "can yield 0 progress messages if we so desire", make_server:

        class Handler(SimpleWebSocketBase):
            def transform_progress(s, body, message, **kwargs):
                if message == "ignore":
                    return
                yield {"progress": message}

            async def process_message(s, path, body, message_id, message_key, progress_cb):
                progress_cb("hello")
                progress_cb("ignore")
                progress_cb("there")
                return "blah"

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                message_id = await stream.start("/one/two", {"hello": "there"})

                await stream.check_reply({"progress": "hello"}, message_id=message_id)
                await stream.check_reply({"progress": "there"}, message_id=message_id)
                await stream.check_reply("blah", message_id=message_id)

    async it "can yield multiple progress messages if we so desire", make_server:

        class Handler(SimpleWebSocketBase):
            def transform_progress(s, body, message, **kwargs):
                for m in message:
                    yield {"progress": m}

            async def process_message(s, path, body, message_id, message_key, progress_cb):
                progress_cb(["hello", "people"])
                return "blah"

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                message_id = await stream.start("/one/two", {"hello": "there"})

                await stream.check_reply({"progress": "hello"}, message_id=message_id)
                await stream.check_reply({"progress": "people"}, message_id=message_id)
                await stream.check_reply("blah", message_id=message_id)

    async it "calls the message_done callback", make_server:
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

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                message_id = await stream.start("/one/two", {"hello": "there"})

                await stream.check_reply({"progress": "hello"}, message_id=message_id)
                await stream.check_reply("blah", message_id=message_id)

                assert info["message_key"] is not None
                pytest.helpers.assertComparison(
                    called,
                    [
                        "process",
                        (
                            {
                                "path": "/one/two",
                                "body": {"hello": "there"},
                                "message_id": message_id,
                            },
                            "blah",
                            info["message_key"],
                            None,
                        ),
                    ],
                    is_json=True,
                )

    async it "sends back done true if msg is None", make_server:
        info = {"message_key": None}
        called = []

        class Handler(SimpleWebSocketBase):
            def message_done(s, request, final, message_key, exc_info=None):
                called.append((request, final, message_key, exc_info))

            async def process_message(s, path, body, message_id, message_key, progress_cb):
                info["message_key"] = message_key
                called.append("process")
                progress_cb("hello")

        message_id = str(uuid.uuid1())
        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                message_id = await stream.start("/one/two", {"hello": "there"})

                await stream.check_reply({"progress": "hello"}, message_id=message_id)

                assert len(server.wsconnections) == 0
                assert info["message_key"] is not None
                assert called == [
                    "process",
                    (
                        {
                            "path": "/one/two",
                            "body": {"hello": "there"},
                            "message_id": message_id,
                        },
                        None,
                        info["message_key"],
                        None,
                    ),
                ]

                await stream.check_reply({"done": True}, message_id=message_id)

    async it "calls the message_done with exc_info if an exception is raised in process_message", make_server:
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
        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                message_id = await stream.start("/one/two", {"hello": "there"})

                await stream.check_reply({"progress": "hello"}, message_id=message_id)

                reply = {
                    "error": "Internal Server Error",
                    "error_code": "InternalServerError",
                    "status": 500,
                }
                await stream.check_reply(
                    reply,
                    message_id=message_id,
                )

            assert info["message_key"] is not None

            class ATraceback:
                def __eq__(s, other):
                    return isinstance(other, types.TracebackType)

            assert called == [
                "process",
                (
                    {"path": "/one/two", "body": {"hello": "there"}, "message_id": message_id},
                    reply,
                    info["message_key"],
                    (ValueError, error, ATraceback()),
                ),
            ]

    async it "message_done can be used to close the connection", make_server:
        info = {"message_key": None}
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
        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                message_id = await stream.start("/one/two", {"hello": "there"})

                await stream.check_reply({"progress": "there"}, message_id=message_id)
                await stream.check_reply({"one": "two"}, message_id=message_id)

                assert info["message_key"] is not None

                assert called == [
                    "process",
                    (
                        {"path": "/one/two", "body": {"hello": "there"}, "message_id": message_id},
                        {"one": "two"},
                        info["message_key"],
                        None,
                    ),
                ]

    async it "modifies ws_connection object", make_server:

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                assert type(s.key) == str
                assert len(s.key) == 36
                assert message_id != message_key
                assert message_key != s.key
                assert message_key in s.wsconnections
                return "blah"

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                await stream.start("/one/two", {"hello": "there"})
                assert server.wsconnections == {}

    async it "waits for connections to close before ending server", make_server:
        f1 = asyncio.Future()
        f2 = asyncio.Future()

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                f1.set_result(True)
                await asyncio.sleep(0.5)
                f2.set_result(True)
                return "blah"

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                await stream.start("/one/two", {"hello": "there"})

                await f1
                assert len(server.wsconnections) == 1
                assert not f2.done()

        assert f2.result() is True

    async it "can stay open", make_server:
        message_info = {"keys": set(), "message_keys": []}

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                assert path == "/one/two"
                assert body == {"wat": mock.ANY}
                message_info["keys"].add(s.key)
                message_info["message_keys"].append(message_key)
                return body["wat"]

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                message_id = await stream.start("/one/two", {"wat": "one"})
                await stream.check_reply("one", message_id=message_id)

                message_id = await stream.start("/one/two", {"wat": "two"})
                await stream.check_reply("two", message_id=message_id)

        assert len(message_info["keys"]) == 1
        assert len(message_info["message_keys"]) == len(set(message_info["message_keys"]))

    async it "can handle ticks for me", make_server:

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                assert path == "/one/two"
                assert body == {"wat": mock.ANY}
                return body["wat"]

        message_id = str(uuid.uuid1())

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                await stream.start("__tick__", pytest.helpers.Empty, message_id="__tick__")
                await stream.check_reply({"ok": "thankyou"}, message_id="__tick__")

                message_id = await stream.start("/one/two", {"wat": "two"})
                await stream.check_reply("two", message_id=message_id)

    async it "complains if the message is incorrect", make_server:

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

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                for body in invalid:
                    await stream.ws.send_json(body)
                    res = await stream.ws.receive_json()
                    pytest.helpers.assertComparison(
                        res,
                        {
                            "message_id": None,
                            "reply": {"error": mock.ANY, "error_code": "InvalidMessage"},
                        },
                        is_json=True,
                    )

    async it "can do multiple messages at the same time", make_server:

        class Handler(SimpleWebSocketBase):
            do_close = False

            async def process_message(s, path, body, message_id, message_key, progress_cb):
                progress_cb({body["serial"]: ["info", "start"]})
                await asyncio.sleep(body["sleep"])
                return {"processed": body["serial"]}

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:

                message_id1 = str(uuid.uuid1())
                message_id2 = str(uuid.uuid1())

                await stream.ws.send_json(
                    {
                        "path": "/process",
                        "body": {"serial": "1", "sleep": 0.1},
                        "message_id": message_id1,
                    },
                )
                await stream.ws.send_json(
                    {
                        "path": "/process",
                        "body": {"serial": "2", "sleep": 0.05},
                        "message_id": message_id2,
                    },
                )

                pytest.helpers.assertComparison(
                    await stream.ws.receive_json(),
                    {"message_id": message_id1, "reply": {"progress": {"1": ["info", "start"]}}},
                    is_json=True,
                )
                pytest.helpers.assertComparison(
                    await stream.ws.receive_json(),
                    {"message_id": message_id2, "reply": {"progress": {"2": ["info", "start"]}}},
                    is_json=True,
                )
                pytest.helpers.assertComparison(
                    await stream.ws.receive_json(),
                    {"message_id": message_id2, "reply": {"processed": "2"}},
                    is_json=True,
                )
                pytest.helpers.assertComparison(
                    await stream.ws.receive_json(),
                    {"message_id": message_id1, "reply": {"processed": "1"}},
                    is_json=True,
                )

    async it "can close the websocket if we return self.Closing", make_server:

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                if body["close"]:
                    return s.Closing
                else:
                    return "stillalive"

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:

                message_id = str(uuid.uuid1())
                await stream.ws.send_json(
                    {"path": "/process", "body": {"close": False}, "message_id": message_id}
                )
                pytest.helpers.assertComparison(
                    await stream.ws.receive_json(),
                    {
                        "message_id": message_id,
                        "reply": "stillalive",
                    },
                    is_json=True,
                )

                message_id = str(uuid.uuid1())
                await stream.ws.send_json(
                    {"path": "/process", "body": {"close": False}, "message_id": message_id}
                )
                pytest.helpers.assertComparison(
                    await stream.ws.receive_json(),
                    {"message_id": message_id, "reply": "stillalive"},
                    is_json=True,
                )

                message_id = str(uuid.uuid1())
                await stream.ws.send_json(
                    {"path": "/process", "body": {"close": True}, "message_id": message_id}
                )
                pytest.helpers.assertComparison(
                    await stream.ws.receive_json(),
                    {"message_id": message_id, "reply": {"closing": "goodbye"}},
                    is_json=True,
                )

                await stream.ws.receive() is None

    async it "can handle arbitrary json for the body", make_server:

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                return body

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                body = {
                    "one": "two",
                    "three": 4,
                    "five": ["six", "seven", []],
                    "six": [],
                    "seven": True,
                    "eight": False,
                    "nine": {"one": "two", "three": None, "four": {"five": "six"}},
                }

                message_id = await stream.start("/process", body)
                await stream.check_reply(body, message_id=message_id)

    async it "can handle exceptions in process_message", make_server:

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

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                message_id = await stream.start("/error", {"error": "one"})

                await stream.check_reply(
                    {
                        "error": "Internal Server Error",
                        "error_code": "InternalServerError",
                        "status": 500,
                    },
                    message_id=message_id,
                )

                message_id2 = await stream.start("/error", {"error": "two"})
                await stream.check_reply(
                    {"error": {"error": "Try again"}, "error_code": "BadError"},
                    message_id=message_id2,
                )

    async it "can handle a return that has as_dict on it", make_server:

        class Ret:
            def __init__(s, value):
                s.value = value

            def as_dict(s):
                return {"result": "", "value": s.value}

        class Handler(SimpleWebSocketBase):
            async def process_message(s, path, body, message_id, message_key, progress_cb):
                return Ret("blah and stuff")

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:
                message_id = await stream.start("/thing", {})
                await stream.check_reply(
                    {"result": "", "value": "blah and stuff"}, message_id=message_id
                )

    async it "can process replies", make_server:
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

        async with make_server(Handler) as server:
            async with server.ws_stream() as stream:

                ##################
                ### NO_ERROR

                message_id = await stream.start("/no_error", {})
                await stream.check_reply({"success": True}, message_id=message_id)

                ##################
                ### INTERNAL_ERROR

                message_id = await stream.start("/internal_error", {})
                await stream.check_reply(
                    {
                        "error": "Internal Server Error",
                        "error_code": "InternalServerError",
                        "status": 500,
                    },
                    message_id=message_id,
                )

                ##################
                ### CUSTOM RETURN

                message_id = await stream.start("/custom_return", {})
                await stream.check_reply({"progress": {"error": "progress"}}, message_id=message_id)
                await stream.check_reply({"error": "Stuff", "status": 400}, message_id=message_id)

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
