# coding: spec

from whirlwind.store import pass_on_result, ProcessItem

from delfick_project.errors_pytest import assertRaises
from unittest import mock
import asynctest
import asyncio
import pytest

describe "pass_on_result":

    @pytest.fixture()
    def run_pass(self):
        async def run_pass(fut, side_effect, on_command=True, log_exceptions=False):
            command = mock.Mock(name="command")

            kwargs = {}
            if isinstance(side_effect, BaseException):
                kwargs["side_effect"] = side_effect
            else:
                kwargs["return_value"] = side_effect

            execute = asynctest.mock.CoroutineMock(name="task", **kwargs)
            if on_command:
                command.execute = execute
                execute = None

            return await pass_on_result(fut, command, execute, log_exceptions=True)

        return run_pass

    @pytest.fixture()
    def combinations(self):
        return [
            {"on_command": True, "log_exceptions": False},
            {"on_command": True, "log_exceptions": True},
            {"on_command": False, "log_exceptions": False},
            {"on_command": False, "log_exceptions": True},
        ]

    async it "passes on a cancellation", run_pass, combinations:
        for combination in combinations:
            fut = asyncio.Future()
            with assertRaises(asyncio.CancelledError):
                await run_pass(fut, asyncio.CancelledError(), **combination)
            assert fut.cancelled()

    async it "passes on an exception", run_pass, combinations:

        class E(Exception):
            pass

        for combination in combinations:
            fut = asyncio.Future()
            error = E("WAT")
            with assertRaises(E, "WAT"):
                await run_pass(fut, error, **combination)
            assert fut.exception() is error

    async it "passes on a result", run_pass, combinations:
        result = mock.NonCallableMock(name="result")

        for combination in combinations:
            fut = asyncio.Future()
            assert await run_pass(fut, result, **combination) is result
            assert (await fut) is result

    async it "does nothing to fut if it's already cancelled", run_pass, combinations:

        class E(Exception):
            pass

        error = E("WAT")
        result = mock.NonCallableMock(name="result")
        cancelled_error = asyncio.CancelledError()

        fut = asyncio.Future()
        fut.cancel()

        for combination in combinations:
            for side_effect in (error, result, cancelled_error):
                with assertRaises(asyncio.CancelledError):
                    await run_pass(fut, side_effect, **combination)
                assert fut.cancelled()

    async it "does nothing to fut already has an exception", run_pass, combinations:

        class E(Exception):
            pass

        class E2(Exception):
            pass

        error = E("WAT")
        result = mock.NonCallableMock(name="result")
        cancelled_error = asyncio.CancelledError()

        fut = asyncio.Future()
        fut_error = E2("HELLO")
        fut.set_exception(fut_error)

        for combination in combinations:
            for side_effect in (error, result, cancelled_error):
                with assertRaises(E2, "HELLO"):
                    await run_pass(fut, side_effect, **combination)
                assert fut.exception() is fut_error

    async it "does nothing to fut already has a result", run_pass, combinations:

        class E(Exception):
            pass

        error = E("WAT")
        result = mock.NonCallableMock(name="result")
        cancelled_error = asyncio.CancelledError()

        fut = asyncio.Future()
        fut_result = mock.NonCallableMock(name="fut_result")
        fut.set_result(fut_result)

        for combination in combinations:
            for side_effect in (error, result, cancelled_error):
                assert (await run_pass(fut, side_effect, **combination)) is fut_result
                assert (await fut) is fut_result

describe "ProcessItem":
    it "takes in some things and understands a non interactive Command":
        fut = asyncio.Future()

        class Command:
            def execute(self):
                pass

        command = Command()
        execute = mock.Mock(name="execute")
        messages = mock.Mock(name="messages")

        item = ProcessItem(fut, command, execute, messages)

        assert item.fut is fut
        assert item.execute is execute
        assert item.command is command
        assert item.messages is messages
        assert not item.interactive

    it "takes in some things and understands an interactive Command":
        fut = asyncio.Future()

        class Command:
            def execute(self, messages):
                pass

        command = Command()
        execute = mock.Mock(name="execute")
        messages = mock.Mock(name="messages")

        item = ProcessItem(fut, command, execute, messages)

        assert item.fut is fut
        assert item.execute is execute
        assert item.command is command
        assert item.messages is messages
        assert item.interactive

    describe "process":

        @pytest.fixture()
        def messages(self):
            class Messages:
                def __init__(s):
                    s.ts = []

            return Messages()

        @pytest.fixture()
        def item_maker(self, messages):
            def make_item(fut, side_effect, on_command=True):
                command = mock.Mock(name="command")
                execute = asynctest.mock.CoroutineMock(name="execute")

                if isinstance(side_effect, BaseException):
                    execute.side_effect = side_effect
                else:
                    execute.return_value = side_effect

                if on_command:
                    command.execute = execute
                    execute = None

                return ProcessItem(fut, command, execute, messages)

            return make_item

        it "fails the future if pass_on_result itself fails", messages, item_maker:
            error = Exception("STUFF")
            pass_on_result = mock.Mock(name="pass_on_result", side_effect=error)

            fut = asyncio.Future()
            with mock.patch("whirlwind.store.pass_on_result", pass_on_result):
                assert item_maker(fut, None).process() is fut

            assert fut.exception() is error
            assert messages.ts == []

        async it "returns a task from pass_on_result", messages, item_maker:
            fut = asyncio.Future()
            task = item_maker(fut, asyncio.CancelledError()).process()
            assert messages.ts == [(task, False, True)]
            with assertRaises(asyncio.CancelledError):
                await task
            assert fut.cancelled()
            messages.ts.clear()

            class E(Exception):
                pass

            error = E("THINGS")
            fut = asyncio.Future()
            task = item_maker(fut, error).process()
            assert messages.ts == [(task, False, True)]
            with assertRaises(E, "THINGS"):
                await task
            assert fut.exception() is error
            messages.ts.clear()

            result = mock.Mock(name="result")
            fut = asyncio.Future()
            task = item_maker(fut, result).process()
            assert messages.ts == [(task, False, True)]
            assert (await task) is result
            assert (await fut) is result
