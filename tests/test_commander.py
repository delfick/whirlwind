# coding: spec

from whirlwind.commander import Commander
from whirlwind import test_helpers as thp
from whirlwind.store import Store

from option_merge.formatter import MergedOptionStringFormatter
from input_algorithms.errors import BadSpecValue
from input_algorithms.dictobj import dictobj
from input_algorithms import spec_base as sb
from unittest import mock
import uuid

class Formatter(MergedOptionStringFormatter):
    def special_get_field(self, *args, **kwargs):
        pass

    def special_format_field(self, *args, **kwargs):
        pass

store = Store(default_path="/v1", formatter=Formatter)

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
        return await self.executor.execute("/v1", {"command": "thing", "args": {"value": f"called! {self.passon}"}})

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

describe thp.AsyncTestCase, "Commander":
    @thp.with_timeout
    async it "works":
        other = mock.Mock(name="other")
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store, other=other)

        value = str(uuid.uuid1())
        thing, val = await commander.executor(progress_cb, request_handler).execute(
              "/v1"
            , {"command": "thing", "args": {"value": value}}
            )

        self.assertEqual(val, value)

        self.assertIs(thing.other, other)
        self.assertIs(thing.commander, commander)
        self.assertIs(thing.progress_cb, progress_cb)
        self.assertIs(thing.request_handler, request_handler)
        self.assertEqual(thing.path, "/v1")
        self.assertIs(thing.store, store)

        assert thing.request_future.done()

    @thp.with_timeout
    async it "can be given an executor":
        other = mock.Mock(name="other")
        other2 = mock.Mock(name="other2")
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store, other=other)

        value = str(uuid.uuid1())
        thing, val = await commander.executor(progress_cb, request_handler, other=other2).execute(
              "/v1"
            , {"command": "thing_caller", "args": {"passon": value}}
            )

        self.assertEqual(val, f"called! {value}")

        self.assertIs(thing.other, other2)
        self.assertIs(thing.commander, commander)
        self.assertIs(thing.progress_cb, progress_cb)
        self.assertIs(thing.request_handler, request_handler)
        self.assertEqual(thing.path, "/v1")
        self.assertIs(thing.store, store)

        assert thing.request_future.done()

    @thp.with_timeout
    async it "injected fields complain if they don't exist":
        store2 = store.clone()
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store2)

        try:
            await commander.executor(progress_cb, request_handler).execute(
                  "/v1"
                , {"command": "fields_are_required"}
                )
            assert False, "expected an error"
        except KeyError as error:
            self.assertEqual(str(error), "<Path(notexisting)>")

    @thp.with_timeout
    async it "injected fields complain if they don't match format_into option":
        store2 = store.clone()
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store2)

        try:
            await commander.executor(progress_cb, request_handler, option="asdf").execute(
                  "/v1"
                , {"command": "injected_can_have_format_into"}
                )
            assert False, "expected an error"
        except BadSpecValue as error:
            self.assertEqual(len(error.errors), 1)
            error = error.errors[0]
            assert isinstance(error, BadSpecValue)
            self.assertEqual(error.message, "Expected an integer")

    @thp.with_timeout
    async it "injected fields do not come from args":
        store2 = store.clone()
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store2)

        try:
            await commander.executor(progress_cb, request_handler).execute(
                  "/v1"
                , {"command": "injected_can_have_format_into", "args": {"option": "asdf"}}
                )
            assert False, "expected an error"
        except KeyError as error:
            self.assertEqual(str(error), "<Path(option)>")

    @thp.with_timeout
    async it "injected fields can be nullable":
        store2 = store.clone()
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store2)

        got = await commander.executor(progress_cb, request_handler).execute(
             "/v1"
           , {"command": "injected_values_can_be_nullable"}
           )
        self.assertEqual(got, {"optional": None})

        value = str(uuid.uuid4())
        got2 = await commander.executor(progress_cb, request_handler, optional=value).execute(
             "/v1"
           , {"command": "injected_values_can_be_nullable"}
           )
        self.assertEqual(got2, {"optional": value})

    @thp.with_timeout
    async it "can override values":
        store2 = store.clone()

        other1 = mock.Mock(name="other")
        other2 = mock.Mock(name="other2")
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store2, other=other1)

        value = str(uuid.uuid1())
        thing, val = await commander.executor(progress_cb, request_handler).execute(
              "/v1"
            , {"command": "thing", "args": {"value": value}}
            , {"other": other2}
            )

        self.assertEqual(val, value)
        self.assertIs(thing.other, other2)
        self.assertIs(thing.store, store2)
        self.assertIsNot(store, store2)

    @thp.with_timeout
    async it "can inject values that are dictobj's":
        class Other(dictobj):
            fields = ["one"]

        other = Other("twenty")
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store, other=other)

        value = str(uuid.uuid1())
        thing, val = await commander.executor(progress_cb, request_handler).execute(
              "/v1"
            , {"command": "thing", "args": {"value": value}}
            )

        self.assertEqual(val, value)
        self.assertIs(thing.other, other)
