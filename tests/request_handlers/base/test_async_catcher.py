# coding: spec

from whirlwind.request_handlers.base import AsyncCatcher, Finished, MessageFromExc, reprer
from whirlwind.test_helpers import AsyncTestCase

from noseOfYeti.tokeniser.async_support import async_noy_sup_setUp
from unittest import mock, TestCase
import binascii
import asyncio
import types
import uuid
import json


class ATraceback:
    def __eq__(self, other):
        return isinstance(other, types.TracebackType)


describe TestCase, "reprer":
    it "reprs random objects":

        class Other:
            def __repr__(self):
                return "<<<OTHER>>>"

        thing = {"status": 301, "other": Other()}
        got = json.dumps(thing, default=reprer)

        expected = {"status": 301, "other": "<<<OTHER>>>"}
        self.assertEqual(json.loads(got), expected)

    it "hexlifies bytes objects":
        val = str(uuid.uuid1()).replace("-", "")
        unhexlified = binascii.unhexlify(val)

        thing = {"status": 302, "thing": unhexlified}
        got = json.dumps(thing, default=reprer)

        expected = {"status": 302, "thing": val}
        self.assertEqual(json.loads(got), expected)

describe TestCase, "MessageFromExc":
    it "returns the kwargs from a Finished":
        error = Finished(status=418, one=1)
        info = MessageFromExc()(Finished, error, None)
        self.assertEqual(info, {"status": 418, "one": 1})

    it "uses process if not a finished":
        message_from_exc = MessageFromExc()
        exc_type = mock.Mock(name="exc_type")
        exc = mock.Mock(nme="exc")
        tb = mock.Mock(name="tb")
        info = mock.Mock(name="info")
        process = mock.Mock(name="process", return_value=info)

        exc = mock.Mock(name="exc")

        with mock.patch.object(message_from_exc, "process", process):
            self.assertIs(message_from_exc(exc_type, exc, tb), info)

        process.assert_called_once_with(exc_type, exc, tb)

    it "creates an internal server error by default":
        info = MessageFromExc()(ValueError, ValueError("wat"), None)
        self.assertEqual(
            info,
            {"status": 500, "error": "Internal Server Error", "error_code": "InternalServerError"},
        )

describe AsyncTestCase, "AsyncCatcher":
    async it "takes in the request, info and final":
        request = mock.Mock(name="request")
        info = mock.Mock(name="info")
        final = mock.Mock(name="final")
        catcher = AsyncCatcher(request, info, final=final)
        self.assertIs(catcher.request, request)
        self.assertIs(catcher.info, info)
        self.assertIs(catcher.final, final)

    async it "defaults final to None":
        request = mock.Mock(name="request")
        info = mock.Mock(name="info")
        catcher = AsyncCatcher(request, info)
        self.assertIs(catcher.info, info)
        self.assertIs(catcher.final, None)

    describe "Behaviour":
        async before_each:
            self.info = {}
            self.request = mock.Mock(name="request")
            self.catcher = AsyncCatcher(self.request, self.info)

        async it "completes with the result from info if no exception is raised":
            result = str(uuid.uuid1())

            fake_complete = mock.Mock(name="complete")
            with mock.patch.object(self.catcher, "complete", fake_complete):
                async with self.catcher:
                    self.info["result"] = result
                    self.assertEqual(len(fake_complete.mock_calls), 0)

            fake_complete.assert_called_once_with(result, status=200)

        async it "completes with a message from the exception and default status of 500":
            msg = mock.Mock(name="msg")

            error = ValueError("lol")

            fake_complete = mock.Mock(name="complete")
            self.request.message_from_exc.return_value = msg

            with mock.patch.object(self.catcher, "complete", fake_complete):
                async with self.catcher:
                    self.assertEqual(len(fake_complete.mock_calls), 0)
                    self.assertEqual(len(self.request.message_from_exc.mock_calls), 0)
                    raise error

            fake_complete.assert_called_once_with(
                msg, status=500, exc_info=(ValueError, error, ATraceback())
            )
            self.request.message_from_exc.assert_called_once_with(ValueError, error, ATraceback())

        describe "complete":
            async before_each:
                self.exc_info = mock.Mock(name="exc_info")

            async it "calls send_msg with the msg if it's not a dictionary":
                kls = type("kls", (object,), {})
                for thing in (0, 1, [], [1], True, False, None, lambda: 1, kls, kls()):
                    status = mock.Mock(name="status")
                    send_msg = mock.Mock(name="send_msg")
                    with mock.patch.object(self.catcher, "send_msg", send_msg):
                        self.catcher.complete(thing, status=status, exc_info=self.exc_info)
                    send_msg.assert_called_once_with(thing, status=status, exc_info=self.exc_info)

            async it "overrides status with what is found in the dict msg":
                status = mock.Mock(name="status")
                thing = {"status": 300}
                send_msg = mock.Mock(name="send_msg")
                with mock.patch.object(self.catcher, "send_msg", send_msg):
                    self.catcher.complete(thing, status=status)
                send_msg.assert_called_once_with(thing, status=300, exc_info=None)

            async it "reprs random objects":
                result = str(uuid.uuid1())
                self.request.reprer = reprer

                class Other:
                    def __repr__(self):
                        return "<<<OTHER>>>"

                thing = {"status": 301, "other": Other()}
                expected = {"status": 301, "other": "<<<OTHER>>>"}

                status = mock.Mock(name="status")
                send_msg = mock.Mock(name="send_msg")
                with mock.patch.object(self.catcher, "send_msg", send_msg):
                    self.catcher.complete(thing, status=status)
                send_msg.assert_called_once_with(expected, status=301, exc_info=None)

        describe "send_msg":
            async before_each:
                self.request = mock.Mock(name="request", spec=["_finished", "send_msg"])
                self.catcher = AsyncCatcher(self.request, self.info)
                self.exc_info = mock.Mock(name="exc_info")

            async it "does nothing if the request is already finished and ws_connection object":
                msg = mock.Mock(name="msg")
                self.request._finished = True
                self.catcher.send_msg(msg)
                self.assertEqual(len(self.request.send_msg.mock_calls), 0)

            async it "uses request.send_msg if final is None":
                msg = mock.Mock(name="msg")
                status = mock.Mock(name="status")
                self.request._finished = False
                self.catcher.final = None
                self.catcher.send_msg(msg, status=status, exc_info=self.exc_info)
                self.request.send_msg.assert_called_once_with(msg, status, exc_info=self.exc_info)

            async it "uses final if it was specified":
                msg = mock.Mock(name="msg")
                self.request._finished = False

                final = mock.Mock(name="final")
                self.catcher.final = final

                self.catcher.send_msg(msg, exc_info=self.exc_info)
                self.assertEqual(len(self.request.send_msg.mock_calls), 0)
                final.assert_called_once_with(msg, exc_info=self.exc_info)
