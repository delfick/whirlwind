# coding: spec

from whirlwind.request_handlers.base import Simple, Finished, reprer

from tornado.httputil import HTTPHeaders
import asyncio
import pytest
import uuid

describe "Simple without error":
    describe "With no methods":

        @pytest.fixture()
        async def server(self, server_wrapper):
            async with server_wrapper(None, lambda s: [("/", Simple)]) as server:
                yield server

        async it "gets method not supported for all the methods", server:
            for method, body in (
                ("GET", None),
                ("POST", b""),
                ("PUT", b""),
                ("DELETE", None),
                ("PATCH", b""),
            ):
                if body is None:
                    await server.assertHTTP(method, "/", {}, status=405)
                else:
                    await server.assertHTTP(method, "/", {"data": body}, status=405)

    describe "Getting body as json from files":

        @pytest.fixture()
        async def server(self, server_wrapper):
            class FilledSimple(Simple):
                async def process(s):
                    return {
                        "body": s.body_as_json(),
                        "file": s.request.files["attachment"][0]["body"].decode(),
                        "filename": s.request.files["attachment"][0]["filename"],
                    }

                do_put = process
                do_post = process

            async with server_wrapper(None, lambda s: [("/", FilledSimple)]) as server:
                yield server

        async it "works", server:
            boundary = "------WebKitFormBoundaryjdGa6A5qLy18abKk"
            attachment = 'Content-Disposition: form-data; name="attachment"; filename="thing.txt"\r\nContent-Type: text/plain\r\n\r\nhello there\n'
            args = 'Content-Disposition: form-data; name="__body__"; filename="blob"\r\nContent-Type: application/json\r\n\r\n{"command":"attachments/add"}'
            body = f"{boundary}\r\n{attachment}\r\n{boundary}\r\n{args}\r\n{boundary}--"
            headers = HTTPHeaders(
                {
                    "content-type": "multipart/form-data; boundary=----WebKitFormBoundaryjdGa6A5qLy18abKk"
                }
            )

            for method in ("POST", "PUT"):
                expected = {
                    "body": {"command": "attachments/add"},
                    "file": "hello there\n",
                    "filename": "thing.txt",
                }
                await server.assertHTTP(
                    "POST",
                    "/",
                    {"data": body.encode(), "headers": headers},
                    status=200,
                    json_output=expected,
                )

    describe "Uses reprer":

        @pytest.fixture()
        async def server(self, server_wrapper):
            class Thing:
                def __special_repr__(self):
                    return {"special": "|<>THING<>|"}

            def better_reprer(o):
                if isinstance(o, Thing):
                    return o.__special_repr__()
                return reprer(o)

            class FilledSimple(Simple):
                def initialize(s, *args, **kwargs):
                    super().initialize()
                    s.reprer = better_reprer

                async def do_get(s):
                    return {"thing": Thing()}

                async def do_post(s):
                    return {"body": s.body_as_json(), "thing": Thing()}

            async with server_wrapper(None, lambda s: [("/", FilledSimple)]) as server:
                yield server

        async it "works", server:
            await server.assertHTTP(
                "GET", "/", {}, status=200, json_output={"thing": {"special": "|<>THING<>|"}}
            )

            expected = {
                "thing": {"special": "|<>THING<>|"},
                "body": {"one": True},
            }
            await server.assertHTTP(
                "POST", "/", {"json": {"one": True}}, status=200, json_output=expected
            )

    describe "With GET":

        @pytest.fixture()
        def result(self):
            return str(uuid.uuid1())

        @pytest.fixture()
        async def server(self, server_wrapper, result):
            class FilledSimple(Simple):
                async def do_get(s, *, one, two):
                    assert one == "one"
                    assert two == "two"
                    assert s.request.path == "/info/blah/one/two"
                    return result

            path = "/info/blah/(?P<one>.*)/(?P<two>.*)"
            async with server_wrapper(None, lambda s: [(path, FilledSimple)]) as server:
                yield server

        async it "allows GET requests", server, result:
            await server.assertHTTP("GET", "/info/blah/one/two", {}, status=200, text_output=result)

    describe "With POST":

        @pytest.fixture()
        def body(self):
            return str(uuid.uuid1())

        @pytest.fixture()
        def result(self):
            return str(uuid.uuid1())

        @pytest.fixture()
        async def server(self, server_wrapper, body, result):
            class FilledSimple(Simple):
                async def do_post(s, one, two):
                    assert one == "one"
                    assert two == "two"
                    assert s.request.path == "/info/blah/one/two"
                    assert s.request.body == body.encode()
                    return result

            path = "/info/blah/(.*)/(.*)"
            async with server_wrapper(None, lambda s: [(path, FilledSimple)]) as server:
                yield server

        async it "allows POST requests", server, body, result:
            path = "/info/blah/one/two"
            await server.assertHTTP("POST", path, {"data": body}, status=200, text_output=result)

    describe "With PUT":

        @pytest.fixture()
        def body(self):
            return str(uuid.uuid1())

        @pytest.fixture()
        def result(self):
            return str(uuid.uuid1())

        @pytest.fixture()
        async def server(self, server_wrapper, body, result):
            class FilledSimple(Simple):
                async def do_put(s, one, two):
                    assert one == "one"
                    assert two == "two"
                    assert s.request.path == "/info/blah/one/two"
                    assert s.request.body == body.encode()
                    return result

            path = "/info/blah/(.*)/(.*)"
            async with server_wrapper(None, lambda s: [(path, FilledSimple)]) as server:
                yield server

        async it "allows PUT requests", server, body, result:
            path = "/info/blah/one/two"
            await server.assertHTTP("PUT", path, {"data": body}, status=200, text_output=result)

    describe "With PATCH":

        @pytest.fixture()
        def body(self):
            return str(uuid.uuid1())

        @pytest.fixture()
        def result(self):
            return str(uuid.uuid1())

        @pytest.fixture()
        async def server(self, server_wrapper, body, result):
            class FilledSimple(Simple):
                async def do_patch(s, one, two):
                    assert one == "one"
                    assert two == "two"
                    assert s.request.path == "/info/blah/one/two"
                    assert s.request.body == body.encode()
                    return result

            path = "/info/blah/(.*)/(.*)"
            async with server_wrapper(None, lambda s: [(path, FilledSimple)]) as server:
                yield server

        async it "allows PATCH requests", server, body, result:
            path = "/info/blah/one/two"
            await server.assertHTTP("PATCH", path, {"data": body}, status=200, text_output=result)

    describe "With DELETE":

        @pytest.fixture()
        def body(self):
            return str(uuid.uuid1())

        @pytest.fixture()
        def result(self):
            return str(uuid.uuid1())

        @pytest.fixture()
        async def server(self, server_wrapper, body, result):
            class FilledSimple(Simple):
                async def do_delete(s, one, two):
                    assert one == "one"
                    assert two == "two"
                    assert s.request.path == "/info/blah/one/two"
                    assert s.request.body == body.encode()
                    return result

            path = "/info/blah/(.*)/(.*)"
            async with server_wrapper(None, lambda s: [(path, FilledSimple)]) as server:
                yield server

        async it "allows DELETE requests", server, body, result:
            path = "/info/blah/one/two"
            await server.assertHTTP("DELETE", path, {"data": body}, status=200, text_output=result)


describe "no ws_connection object":

    @pytest.fixture()
    def fut(self):
        return asyncio.get_event_loop().create_future()

    @pytest.fixture()
    async def server(self, fut, server_wrapper):
        class FilledSimple(Simple):
            async def do_get(s):
                s.send_msg({"other": "stuff"})
                assert not hasattr(s, "ws_connection")
                fut.set_result(True)
                return {"thing": "blah"}

        async with server_wrapper(None, lambda s: [("/", FilledSimple)]) as server:
            yield server

    async it "has no ws_connection", server, fut:
        await server.assertHTTP("GET", "/", {}, status=200, json_output={"other": "stuff"})
        assert fut.done()

describe "Simple with error":

    @pytest.fixture()
    def reason(self):
        return str(uuid.uuid1())

    @pytest.fixture()
    def path(self):
        return "/info/blah"

    describe "With GET":

        @pytest.fixture()
        async def server(self, server_wrapper, reason, path):
            class FilledSimple(Simple):
                async def do_get(s):
                    assert s.request.path == path
                    raise Finished(status=501, reason=reason)

            async with server_wrapper(None, lambda s: [(path, FilledSimple)]) as server:
                yield server

        async it "allows GET requests", server, path, reason:
            await server.assertHTTP(
                "GET", path, {}, status=501, json_output={"status": 501, "reason": reason}
            )

    describe "With POST":

        @pytest.fixture()
        async def server(self, server_wrapper, reason, path):
            class FilledSimple(Simple):
                async def do_post(s):
                    assert s.request.path == path
                    raise Finished(status=501, reason=reason)

            async with server_wrapper(None, lambda s: [(path, FilledSimple)]) as server:
                yield server

        async it "allows POST requests", server, path, reason:
            await server.assertHTTP(
                "POST", path, {}, status=501, json_output={"status": 501, "reason": reason}
            )

    describe "With PUT":

        @pytest.fixture()
        async def server(self, server_wrapper, reason, path):
            class FilledSimple(Simple):
                async def do_put(s):
                    assert s.request.path == path
                    raise Finished(status=501, reason=reason)

            async with server_wrapper(None, lambda s: [(path, FilledSimple)]) as server:
                yield server

        async it "allows PUT requests", server, path, reason:
            await server.assertHTTP(
                "PUT", path, {}, status=501, json_output={"status": 501, "reason": reason}
            )

    describe "With PATCH":

        @pytest.fixture()
        async def server(self, server_wrapper, reason, path):
            class FilledSimple(Simple):
                async def do_patch(s):
                    assert s.request.path == path
                    raise Finished(status=501, reason=reason)

            async with server_wrapper(None, lambda s: [(path, FilledSimple)]) as server:
                yield server

        async it "allows PATCH requests", server, path, reason:
            await server.assertHTTP(
                "PATCH", path, {}, status=501, json_output={"status": 501, "reason": reason}
            )

    describe "With DELETE":

        @pytest.fixture()
        async def server(self, server_wrapper, reason, path):
            class FilledSimple(Simple):
                async def do_delete(s):
                    assert s.request.path == path
                    raise Finished(status=501, reason=reason)

            async with server_wrapper(None, lambda s: [(path, FilledSimple)]) as server:
                yield server

        async it "allows DELETE requests", server, path, reason:
            await server.assertHTTP(
                "DELETE", path, {}, status=501, json_output={"status": 501, "reason": reason}
            )
