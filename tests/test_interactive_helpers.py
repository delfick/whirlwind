# coding: spec

from whirlwind.store import pass_on_result, ProcessItem, MessageHolder

from delfick_project.errors_pytest import assertRaises
from unittest import mock
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

            execute = pytest.helpers.AsyncMock(name="task", **kwargs)
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

    describe "no process":
        async it "just sets the fut to received True":
            fut = asyncio.Future()
            item = ProcessItem(fut, None, None, None)
            item.no_process()
            assert (await fut) == {"received": True}

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
                execute = pytest.helpers.AsyncMock(name="execute")

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

describe "MessageHolder":
    it "takes in command and final_future":
        command = mock.Mock(name="command")
        final_future = asyncio.Future()

        holder = MessageHolder(command, final_future)

        assert holder.ts == []
        assert holder.command is command
        assert isinstance(holder.queue, asyncio.Queue)
        assert holder.final_future is final_future

    it "can be given a main_task":
        holder = MessageHolder(mock.Mock(name="command"), asyncio.Future())
        assert not hasattr(holder, "main_task")

        task = mock.Mock(name="task")
        holder.add_main_task(task)
        assert holder.main_task is task

    describe "add":

        @pytest.fixture()
        def holder(self):
            return MessageHolder(mock.Mock(name="command"), asyncio.Future())

        async it "can be given a command without execute", holder:
            fut = asyncio.Future()
            command = mock.Mock(name="command")
            await holder.add(fut, command)
            assert holder.ts == [(fut, False, True)]

            item = await holder.queue.get()
            assert isinstance(item, ProcessItem)

            assert item.fut is fut
            assert item.command is command
            assert item.execute is None
            assert item.messages is holder

    describe "async iteration":

        @pytest.fixture()
        def final_future(self):
            return asyncio.Future()

        @pytest.fixture()
        def process_item_mock(self):
            return mock.Mock(name="process_item_mock")

        @pytest.fixture()
        async def holder(self, final_future, process_item_mock):
            holder = MessageHolder(mock.Mock(name="command"), final_future)

            async def get():
                async for message in holder:
                    process_item_mock(message)

            t = asyncio.get_event_loop().create_task(get())
            try:
                yield t, holder
            finally:
                t.cancel()
                await asyncio.wait([t])

        async it "gets items off the queue until final_future is done", final_future, holder, process_item_mock:
            t, holder = holder

            f1 = asyncio.Future()
            f2 = asyncio.Future()
            f3 = asyncio.Future()

            c1 = mock.Mock(name="c1")
            c2 = mock.Mock(name="c2")
            c3 = mock.Mock(name="c3")

            got = []

            def process(message):
                got.append(message)
                if message.command is c2:
                    final_future.cancel()

            process_item_mock.side_effect = process

            await holder.add(f1, c1)
            await holder.add(f2, c2)
            await holder.add(f3, c3)

            await t

            assert len(got) == 2
            assert got[0].fut is f1
            assert got[0].command is c1

            assert got[1].fut is f2
            assert got[1].command is c2

            # The three we added
            assert len(holder.ts) == 3

        async it "cancels the getter if final_future is cancelled", final_future, holder:
            t, holder = holder

            final_future.cancel()

            await t

            assert len(holder.ts) == 1
            assert holder.ts[0][0].cancelled()

    describe "finish":
        async it "transfers exception from main_task to tasks with do_transfer to true":
            t1 = asyncio.Future()
            t2 = asyncio.Future()

            t3 = asyncio.Future()
            t3.set_result("DONE")

            class E(Exception):
                pass

            error = E("WAT")
            main_task = asyncio.Future()
            main_task.set_exception(error)

            holder = MessageHolder(mock.Mock(name="command"), asyncio.Future())
            holder.add_main_task(main_task)

            holder.ts = [(t1, True, True), (t2, True, False), (t3, True, True)]
            await holder.finish()

            with assertRaises(E, "WAT"):
                await t1
            with assertRaises(asyncio.CancelledError):
                await t2
            assert (await t3) == "DONE"

        async it "cancels tasks if cancelled is true":
            t1 = asyncio.Future()
            t2 = asyncio.Future()

            t3 = asyncio.Future()
            t3.set_result("DONE")

            main_task = asyncio.Future()

            holder = MessageHolder(mock.Mock(name="command"), asyncio.Future())
            holder.add_main_task(main_task)

            holder.ts = [(t1, True, True), (t2, True, False), (t3, True, True)]
            await holder.finish(cancelled=True)

            with assertRaises(asyncio.CancelledError):
                await t1
            with assertRaises(asyncio.CancelledError):
                await t2
            assert (await t3) == "DONE"

        async it "does not cancel not do_cancel tasks if cancelled is false and main_task not errored":
            t1 = asyncio.Future()
            t2 = asyncio.Future()

            t3 = asyncio.Future()
            t3.set_result("DONE")

            main_task = asyncio.Future()

            holder = MessageHolder(mock.Mock(name="command"), asyncio.Future())
            holder.add_main_task(main_task)

            holder.ts = [(t1, False, True), (t2, False, False), (t3, True, True)]

            called = []

            async def finisher():
                called.append("START")
                await holder.finish(cancelled=False)
                called.append("DONE")

            t = asyncio.get_event_loop().create_task(finisher())
            try:
                await asyncio.sleep(0.1)

                called.append("STOP t1")
                t1.set_result(None)

                called.append("STOP t2")
                t2.set_result(None)

                await t

                assert called == ["START", "STOP t1", "STOP t2", "DONE"]
            finally:
                t.cancel()
                await asyncio.wait([t])

        async it "does cancel do_cancel tasks if cancelled is false and main_task not errored":
            t1 = asyncio.Future()
            t2 = asyncio.Future()

            t3 = asyncio.Future()
            t3.set_result("DONE")

            main_task = asyncio.Future()

            holder = MessageHolder(mock.Mock(name="command"), asyncio.Future())
            holder.add_main_task(main_task)

            holder.ts = [(t1, False, True), (t2, True, False), (t3, True, True)]

            called = []

            async def finisher():
                called.append("START")
                await holder.finish(cancelled=False)
                called.append("DONE")

            t = asyncio.get_event_loop().create_task(finisher())
            try:
                await asyncio.sleep(0.1)

                assert t2.cancelled()

                called.append("STOP t1")
                t1.set_result(None)

                await t

                assert called == ["START", "STOP t1", "DONE"]
            finally:
                t.cancel()
                await asyncio.wait([t])

        async it "does cancel not do_cancel tasks if main task is cancelled":
            t1 = asyncio.Future()
            t2 = asyncio.Future()

            t3 = asyncio.Future()
            t3.set_result("DONE")

            main_task = asyncio.Future()
            main_task.cancel()

            holder = MessageHolder(mock.Mock(name="command"), asyncio.Future())
            holder.add_main_task(main_task)

            holder.ts = [(t1, False, True), (t2, True, False), (t3, True, True)]

            await holder.finish(cancelled=False)

            assert t1.cancelled()
            assert t2.cancelled()

        async it "works if no main_task":
            t1 = asyncio.Future()
            t2 = asyncio.Future()

            t3 = asyncio.Future()
            t3.set_result("DONE")

            holder = MessageHolder(mock.Mock(name="command"), asyncio.Future())

            holder.ts = [(t1, False, True), (t2, True, False), (t3, True, True)]

            await holder.finish(cancelled=True)

            assert t1.cancelled()
            assert t2.cancelled()
