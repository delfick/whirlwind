# coding: spec

from whirlwind.commander import Commander
from whirlwind import test_helpers as thp
from whirlwind.store import Store

from option_merge.formatter import MergedOptionStringFormatter
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

@store.command("thing")
class Thing(store.Command):
    other = store.injected("other")
    commander = store.injected("commander")
    progress_cb = store.injected("progress_cb")
    request_future = store.injected("request_future")
    request_handler = store.injected("request_handler")

    value = dictobj.Field(sb.string_spec, wrapper=sb.required)

    async def execute(self):
        assert not self.request_future.done()
        return self, self.value

describe thp.AsyncTestCase, "Commander":
    @thp.with_timeout
    async it "works":
        other = mock.Mock(name="other")
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store.command_spec, other=other)

        value = str(uuid.uuid1())
        thing, val = await commander.execute(
              "/v1"
            , {"command": "thing", "args": {"value": value}}
            , progress_cb
            , request_handler
            )

        self.assertEqual(val, value)

        self.assertIs(thing.other, other)
        self.assertIs(thing.commander, commander)
        self.assertIs(thing.progress_cb, progress_cb)
        self.assertIs(thing.request_handler, request_handler)

        assert thing.request_future.done()

    @thp.with_timeout
    async it "can override values":
        other1 = mock.Mock(name="other")
        other2 = mock.Mock(name="other2")
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store.command_spec, other=other1)

        value = str(uuid.uuid1())
        thing, val = await commander.execute(
              "/v1"
            , {"command": "thing", "args": {"value": value}}
            , progress_cb
            , request_handler
            , {"other": other2}
            )

        self.assertEqual(val, value)
        self.assertIs(thing.other, other2)

    @thp.with_timeout
    async it "can inject values that are dictobj's":
        class Other(dictobj):
            fields = ["one"]

        other = Other("twenty")
        progress_cb = mock.Mock(name="progress_cb")
        request_handler = mock.Mock(name="request_handler")
        commander = Commander(store.command_spec, other=other)

        value = str(uuid.uuid1())
        thing, val = await commander.execute(
              "/v1"
            , {"command": "thing", "args": {"value": value}}
            , progress_cb
            , request_handler
            )

        self.assertEqual(val, value)
        self.assertIs(thing.other, other)
