# coding: spec

from whirlwind.commander import Commander
from whirlwind.store import Store

from delfick_project.option_merge import MergedOptionStringFormatter, BadOptionFormat, MergedOptions
from delfick_project.norms import dictobj, sb, BadSpecValue
from delfick_project.errors_pytest import assertRaises
from unittest import mock
import asyncio
import uuid

store = Store(default_path="/v1", formatter=MergedOptionStringFormatter)


@store.command("fields_are_required")
class FieldsRequired(store.Command):
    notexisting = store.injected("notexisting")

    async def execute(self):
        assert False, "Shouldn't make it this far"


@store.command("injected_can_have_format_into")
class InjectedHaveFormatInto(store.Command):
    option = store.injected("option", format_into=sb.integer_spec)

    async def execute(self):
        assert False, "Shouldn't make it this far"


@store.command("injected_values_can_be_nullable")
class NullableInjected(store.Command):
    optional = store.injected("optional", nullable=True)

    async def execute(self):
        return {"optional": self.optional}


@store.command("thing_caller")
class ThingCaller(store.Command):
    executor = store.injected("executor")
    passon = dictobj.Field(sb.string_spec, wrapper=sb.required)
    optional = store.injected("notexisting", nullable=True)

    async def execute(self):
        assert self.optional is None
        return await self.executor.execute(
            "/v1", {"command": "thing", "args": {"value": f"called! {self.passon}"}}
        )


@store.command("thing")
class Thing(store.Command):
    path = store.injected("path")
    other = store.injected("other")
    commander = store.injected("commander")
    progress_cb = store.injected("progress_cb")
    request_future = store.injected("request_future")
    request_handler = store.injected("request_handler")

    value = dictobj.Field(sb.string_spec, wrapper=sb.required)

    store = store.injected("store")

    async def execute(self):
        assert not self.request_future.done()
        return self, self.value


describe "Commander":

    async it "works":
        other = mock.Mock(name="other")
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store, other=other)

        value = str(uuid.uuid1())
        thing, val = await commander.executor(progress_cb, request_handler).execute(
            "/v1", {"command": "thing", "args": {"value": value}}
        )

        assert val == value

        assert thing.other is other
        assert thing.commander is commander
        assert thing.progress_cb is progress_cb
        assert thing.request_handler is request_handler
        assert thing.path == "/v1"
        assert thing.store is store

        assert thing.request_future.done()

    async it "can be given a specific request future":
        other = mock.Mock(name="other")
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store, other=other)
        override_request_future = asyncio.Future()

        value = str(uuid.uuid1())
        thing, val = await commander.executor(progress_cb, request_handler).execute(
            "/v1",
            {"command": "thing", "args": {"value": value}},
            request_future=override_request_future,
        )

        assert val == value

        assert thing.request_future is override_request_future
        assert thing.other is other
        assert thing.commander is commander
        assert thing.progress_cb is progress_cb
        assert thing.request_handler is request_handler
        assert thing.path == "/v1"
        assert thing.store is store

        assert not thing.request_future.done()

    async it "can be given an executor":
        other = mock.Mock(name="other")
        other2 = mock.Mock(name="other2")
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store, other=other)

        value = str(uuid.uuid1())
        thing, val = await commander.executor(progress_cb, request_handler, other=other2).execute(
            "/v1", {"command": "thing_caller", "args": {"passon": value}}
        )

        assert val == f"called! {value}"

        assert thing.other is other2
        assert thing.commander is commander
        assert thing.progress_cb is progress_cb
        assert thing.request_handler is request_handler
        assert thing.path == "/v1"
        assert thing.store is store

        assert thing.request_future.done()

    async it "injected fields complain if they don't exist":
        store2 = store.clone()
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store2)

        with assertRaises(
            BadOptionFormat,
            "Can't find key in options",
            chain=["body.args.notexisting"],
            key="notexisting",
        ):
            await commander.executor(progress_cb, request_handler).execute(
                "/v1", {"command": "fields_are_required"}
            )
            assert False, "expected an error"

    async it "injected fields complain if they don't match format_into option":
        store2 = store.clone()
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store2)

        try:
            await commander.executor(progress_cb, request_handler, option="asdf").execute(
                "/v1", {"command": "injected_can_have_format_into"}
            )
            assert False, "expected an error"
        except BadSpecValue as error:
            assert len(error.errors) == 1
            error = error.errors[0]
            assert isinstance(error, BadSpecValue)
            assert error.message == "Expected an integer"

    async it "injected fields do not come from args":
        store2 = store.clone()
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store2)

        with assertRaises(
            BadOptionFormat, "Can't find key in options", chain=["body.args.option"], key="option",
        ):
            await commander.executor(progress_cb, request_handler).execute(
                "/v1", {"command": "injected_can_have_format_into", "args": {"option": "asdf"}}
            )

    async it "injected fields can be nullable":
        store2 = store.clone()
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store2)

        got = await commander.executor(progress_cb, request_handler).execute(
            "/v1", {"command": "injected_values_can_be_nullable"}
        )
        assert got == {"optional": None}

        value = str(uuid.uuid4())
        got2 = await commander.executor(progress_cb, request_handler, optional=value).execute(
            "/v1", {"command": "injected_values_can_be_nullable"}
        )
        assert got2 == {"optional": value}

    async it "can override values":
        store2 = store.clone()

        other1 = mock.Mock(name="other")
        other2 = mock.Mock(name="other2")
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store2, other=other1)

        value = str(uuid.uuid1())
        thing, val = await commander.executor(progress_cb, request_handler).execute(
            "/v1", {"command": "thing", "args": {"value": value}}, {"other": other2}
        )

        assert val == value
        assert thing.other is other2
        assert thing.store is store2
        assert store is not store2

    async it "can inject values that are dictobj's":

        class Other(dictobj):
            fields = ["one"]

        other = Other("twenty")
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store, other=other)

        value = str(uuid.uuid1())
        thing, val = await commander.executor(progress_cb, request_handler).execute(
            "/v1", {"command": "thing", "args": {"value": value}}
        )

        assert val == value
        assert thing.other is other

    async it "allows commands to be retrieved from a MergedOptions":
        options = MergedOptions.using({"command": FieldsRequired}, dont_prefix=[dictobj])
        assert options["command"] is FieldsRequired
