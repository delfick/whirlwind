# coding: spec

from whirlwind.request_handlers import Simple

from unittest import mock
import pytest
import types
import uuid
import sys

describe "RequestsMixin":

    describe "body as json":

        @pytest.fixture()
        async def server(self, server_wrapper):
            class Handler(Simple):
                async def do_post(s):
                    return str(s.body_as_json())

            async with server_wrapper(None, lambda s: [("/", Handler)]) as server:
                yield server

        async it "complains if the body is empty", server:
            await server.assertHTTP(
                "POST",
                "/",
                {"data": ""},
                status=400,
                json_output={
                    "reason": "Failed to load body as json",
                    "error": mock.ANY,
                    "status": 400,
                },
            )

        async it "complains if the body is not valid json", server:
            await server.assertHTTP(
                "POST",
                "/",
                {"data": "{"},
                status=400,
                json_output={
                    "reason": "Failed to load body as json",
                    "error": mock.ANY,
                    "status": 400,
                },
            ),

        async it "returns as a dictionary if valid", server:
            body = {"one": "two", "three": None, "four": [1, 2]}
            await server.assertHTTP("POST", "/", {"json": body}, status=200, text_output=str(body))

    describe "send_msg":

        @pytest.fixture()
        def replies(self):
            return []

        @pytest.fixture()
        async def server(self, server_wrapper, replies):
            class Handler(Simple):
                def process_reply(s, msg, exc_info=None):
                    return replies.append((msg, exc_info))

                async def do_post(s):
                    body = s.body_as_json()
                    kwargs = {}
                    if "msg" in body:
                        kwargs = {"msg": body["msg"]}
                    elif "error" in body:
                        try:
                            raise ValueError(body["error"])
                        except ValueError:
                            kwargs["msg"] = {"error": "error"}
                            kwargs["exc_info"] = sys.exc_info()

                    elif "exception_status" in body and "exception_response" in body:

                        if body["exception_status"]:

                            class Exc(Exception):
                                status = body["exception_status"]

                        else:

                            class Exc(Exception):
                                pass

                        try:
                            raise Exc()
                        except Exception:
                            kwargs["msg"] = body["exception_response"]
                            kwargs["exc_info"] = sys.exc_info()
                    else:

                        class Thing:
                            def as_dict(s2):
                                return {"blah": "meh"}

                        kwargs["msg"] = Thing()

                    if "status" in body:
                        kwargs["status"] = body["status"]

                    s.send_msg(**kwargs)

            async with server_wrapper(None, lambda s: [("/", Handler)]) as server:
                yield server

        async it "calls as_dict on the message if it has that", server:
            await server.assertHTTP(
                "POST",
                "/",
                {"json": {}},
                status=200,
                json_output={"blah": "meh"},
                expected_headers={"Content-Type": "application/json; charset=UTF-8"},
            )

        async it "is application/json if a list", server:
            body = {"msg": [1, 2, 3]}
            await server.assertHTTP("POST", "/", {"json": body}, status=200, json_output=[1, 2, 3])

        async it "overrides status with what is in the msg", server:
            body = {"msg": {"status": 400, "tree": "branch"}}
            await server.assertHTTP(
                "POST",
                "/",
                {"json": body},
                status=400,
                json_output={"status": 400, "tree": "branch"},
            )

            body = {"msg": {"status": 400, "tree": "branch"}, "status": 500}
            await server.assertHTTP(
                "POST",
                "/",
                {"json": body},
                status=400,
                json_output={"status": 400, "tree": "branch"},
            )

        async it "uses status passed in if no status in msg", server:
            body = {"msg": {"tree": "branch"}, "status": 501}
            await server.assertHTTP(
                "POST", "/", {"json": body}, status=501, json_output={"tree": "branch"}
            )

        async it "overrides status with status on exception if there is one", server:
            body = {"exception_status": 418, "exception_response": {"something": 1}}
            await server.assertHTTP(
                "POST", "/", {"json": body}, status=418, json_output={"something": 1}
            )

        async it "overrides status with status in response msg if one", server:
            body = {"exception_status": None, "exception_response": {"status": 598}}
            await server.assertHTTP(
                "POST", "/", {"json": body}, status=598, json_output={"status": 598}
            )

        async it "status for exceptions is otherwise 500", server:
            body = {"exception_status": None, "exception_response": {"things": "wat"}}
            await server.assertHTTP(
                "POST", "/", {"json": body}, status=500, json_output={"things": "wat"}
            )

        async it "empty body if msg is None", server:
            body = {"msg": None}
            await server.assertHTTP("POST", "/", {"json": body}, status=200, text_output="")

        async it "treats html as html", server:
            msg = "<html><body/></html>"
            body = {"msg": msg}
            await server.assertHTTP(
                "POST",
                "/",
                {"json": body},
                status=200,
                text_output=msg,
                expected_headers={"Content-Type": "text/html; charset=UTF-8"},
            )

            msg = "<!DOCTYPE html><html><body/></html>"
            body = {"msg": msg, "status": 500}
            await server.assertHTTP(
                "POST",
                "/",
                {"json": body},
                status=500,
                text_output=msg,
                expected_headers={"Content-Type": "text/html; charset=UTF-8"},
            )

        async it "treats string as text/plain", server:
            msg = str(uuid.uuid1())
            body = {"msg": msg}
            await server.assertHTTP(
                "POST",
                "/",
                {"json": body},
                status=200,
                text_output=msg,
                expected_headers={"Content-Type": "text/plain; charset=UTF-8"},
            )

            body = {"msg": msg, "status": 403}
            await server.assertHTTP(
                "POST",
                "/",
                {"json": body},
                status=403,
                text_output=msg,
                expected_headers={"Content-Type": "text/plain; charset=UTF-8"},
            )

        async it "processes replies", server, replies:
            await server.assertHTTP("POST", "/", {"json": {"msg": "one"}}, status=200)
            assert replies.pop(0) == ("one", None)

            class ATraceback:
                def __eq__(self, other):
                    return isinstance(other, types.TracebackType)

            class AValueError:
                def __init__(self, msg):
                    self.msg = msg

                def __eq__(self, other):
                    return isinstance(other, ValueError) and str(other) == self.msg

            await server.assertHTTP("POST", "/", {"json": {"error": "wat"}}, status=500)
            assert replies.pop(0) == (
                {"error": "error"},
                (ValueError, AValueError("wat"), ATraceback()),
            )

            # Make sure we got all of them
            assert replies == []
