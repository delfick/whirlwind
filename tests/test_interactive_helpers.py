# coding: spec

from whirlwind.store import pass_on_result

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
