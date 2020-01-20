# coding: spec

from whirlwind.request_handlers.base import AsyncCatcher, Finished, MessageFromExc, reprer

from unittest import mock
import binascii
import asyncio
import pytest
import types
import uuid
import json


class ATraceback:
    def __eq__(self, other):
        return isinstance(other, types.TracebackType)


@pytest.fixture()
def V():
    class V:
        info = {}
        request = mock.Mock(
            name="request", spec=["_finished", "send_msg", "message_from_exc", "reprer"]
        )
        exc_info = mock.Mock(name="exc_info")

        def __init__(s):
            s.catcher = AsyncCatcher(s.request, s.info)

    return V()


describe "reprer":
    it "reprs random objects":

        class Other:
            def __repr__(s):
                return "<<<OTHER>>>"

        thing = {"status": 301, "other": Other()}
        got = json.dumps(thing, default=reprer)

        expected = {"status": 301, "other": "<<<OTHER>>>"}
        assert json.loads(got) == expected

    it "hexlifies bytes objects":
        val = str(uuid.uuid1()).replace("-", "")
        unhexlified = binascii.unhexlify(val)

        thing = {"status": 302, "thing": unhexlified}
        got = json.dumps(thing, default=reprer)

        expected = {"status": 302, "thing": val}
        assert json.loads(got) == expected

describe "MessageFromExc":
    it "returns the kwargs from a Finished":
        error = Finished(status=418, one=1)
        info = MessageFromExc()(Finished, error, None)
        assert info == {"status": 418, "one": 1}

    it "uses process if not a finished":
        message_from_exc = MessageFromExc()
        exc_type = mock.Mock(name="exc_type")
        exc = mock.Mock(nme="exc")
        tb = mock.Mock(name="tb")
        info = mock.Mock(name="info")
        process = mock.Mock(name="process", return_value=info)

        exc = mock.Mock(name="exc")

        with mock.patch.object(message_from_exc, "process", process):
            assert message_from_exc(exc_type, exc, tb) is info

        process.assert_called_once_with(exc_type, exc, tb)

    it "creates an internal server error by default":
        info = MessageFromExc()(ValueError, ValueError("wat"), None)
        assert info == {
            "status": 500,
            "error": "Internal Server Error",
            "error_code": "InternalServerError",
        }

describe "AsyncCatcher":
    async it "takes in the request, info and final":
        request = mock.Mock(name="request")
        info = mock.Mock(name="info")
        final = mock.Mock(name="final")
        catcher = AsyncCatcher(request, info, final=final)
        assert catcher.request is request
        assert catcher.info is info
        assert catcher.final is final

    async it "defaults final to None":
        request = mock.Mock(name="request")
        info = mock.Mock(name="info")
        catcher = AsyncCatcher(request, info)
        assert catcher.info is info
        assert catcher.final is None

    describe "Behaviour":
        async it "completes with the result from info if no exception is raised", V:
            result = str(uuid.uuid1())

            fake_complete = mock.Mock(name="complete")
            with mock.patch.object(V.catcher, "complete", fake_complete):
                async with V.catcher:
                    V.info["result"] = result
                    assert len(fake_complete.mock_calls) == 0

            fake_complete.assert_called_once_with(result, status=200)

        async it "completes with a message from the exception and default status of 500", V:
            msg = mock.Mock(name="msg")

            error = ValueError("lol")

            fake_complete = mock.Mock(name="complete")
            V.request.message_from_exc.return_value = msg

            with mock.patch.object(V.catcher, "complete", fake_complete):
                async with V.catcher:
                    assert len(fake_complete.mock_calls) == 0
                    assert len(V.request.message_from_exc.mock_calls) == 0
                    raise error

            fake_complete.assert_called_once_with(
                msg, status=500, exc_info=(ValueError, error, ATraceback())
            )
            V.request.message_from_exc.assert_called_once_with(ValueError, error, ATraceback())

        describe "complete":
            async it "calls send_msg with the msg if it's not a dictionary", V:
                kls = type("kls", (object,), {})
                for thing in (0, 1, [], [1], True, False, None, lambda: 1, kls, kls()):
                    status = mock.Mock(name="status")
                    send_msg = mock.Mock(name="send_msg")
                    with mock.patch.object(V.catcher, "send_msg", send_msg):
                        V.catcher.complete(thing, status=status, exc_info=V.exc_info)
                    send_msg.assert_called_once_with(thing, status=status, exc_info=V.exc_info)

            async it "overrides status with what is found in the dict msg", V:
                status = mock.Mock(name="status")
                thing = {"status": 300}
                send_msg = mock.Mock(name="send_msg")
                with mock.patch.object(V.catcher, "send_msg", send_msg):
                    V.catcher.complete(thing, status=status)
                send_msg.assert_called_once_with(thing, status=300, exc_info=None)

            async it "reprs random objects", V:
                result = str(uuid.uuid1())
                V.request.reprer = reprer

                class Other:
                    def __repr__(s):
                        return "<<<OTHER>>>"

                thing = {"status": 301, "other": Other()}
                expected = {"status": 301, "other": "<<<OTHER>>>"}

                status = mock.Mock(name="status")
                send_msg = mock.Mock(name="send_msg")
                with mock.patch.object(V.catcher, "send_msg", send_msg):
                    V.catcher.complete(thing, status=status)
                send_msg.assert_called_once_with(expected, status=301, exc_info=None)

        describe "send_msg":

            async it "does nothing if the request is already finished and ws_connection object", V:
                msg = mock.Mock(name="msg")
                V.request._finished = True
                V.catcher.send_msg(msg)
                assert len(V.request.send_msg.mock_calls) == 0

            async it "uses request.send_msg if final is None", V:
                msg = mock.Mock(name="msg")
                status = mock.Mock(name="status")
                V.request._finished = False
                V.catcher.final = None
                V.catcher.send_msg(msg, status=status, exc_info=V.exc_info)
                V.request.send_msg.assert_called_once_with(msg, status, exc_info=V.exc_info)

            async it "uses final if it was specified", V:
                msg = mock.Mock(name="msg")
                V.request._finished = False

                final = mock.Mock(name="final")
                V.catcher.final = final

                V.catcher.send_msg(msg, exc_info=V.exc_info)
                assert len(V.request.send_msg.mock_calls) == 0
                final.assert_called_once_with(msg, exc_info=V.exc_info)
