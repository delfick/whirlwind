# coding: spec

from whirlwind.store import (
    Store,
    NoSuchPath,
    NoSuchParent,
    NonInteractiveParent,
    command_spec,
    create_task,
    CantReuseCommands,
)

from delfick_project.option_merge import MergedOptionStringFormatter
from delfick_project.norms import dictobj, sb, Meta, BadSpecValue
from delfick_project.errors_pytest import assertRaises
from unittest import mock
import asyncio
import uuid

describe "Store":
    it "takes in some things":
        prefix = mock.Mock(name="prefix")
        formatter = mock.Mock(name="formatter")
        default_path = mock.Mock(name="default_path")

        store = Store(prefix=prefix, default_path=default_path, formatter=formatter)

        assert store.prefix is prefix
        assert store.default_path is default_path
        assert store.formatter is formatter
        assert isinstance(store.command_spec, command_spec)
        assert store.command_spec.paths is store.paths

        assert dict(store.paths) == {}

    it "has defaults":
        store = Store()

        assert store.prefix == ""
        assert store.default_path == "/v1"
        assert store.formatter is None

    it "normalises the prefix":
        store = Store(prefix="/somewhere/nice")
        assert store.prefix == "/somewhere/nice/"

    describe "clone":
        it "copies everything":
            one = mock.Mock(name="one")
            two = mock.Mock(name="two")
            three = mock.Mock(name="three")

            formatter = mock.Mock(name="formatter")

            store = Store(prefix="stuff", default_path="/v1/blah", formatter=formatter)
            store.paths["/v1"]["blah"] = one

            store2 = store.clone()
            assert store2.prefix == "stuff/"
            assert store2.default_path == "/v1/blah"
            assert store2.formatter is formatter

            assert dict(store2.paths) == {"/v1": {"blah": one}}

            store2.paths["/v1"]["meh"] = two
            assert dict(store2.paths) == {"/v1": {"blah": one, "meh": two}}
            assert dict(store.paths) == {"/v1": {"blah": one}}

            store2.paths["/v2"]["stuff"] = three
            assert dict(store2.paths) == {"/v2": {"stuff": three}, "/v1": {"blah": one, "meh": two}}
            assert dict(store.paths) == {"/v1": {"blah": one}}

    describe "normalise_prefix":
        it "says None is an empty string":
            store = Store()
            assert store.normalise_prefix(None) == ""

        it "ensures a trailing slash when we have a prefix":
            store = Store()
            assert store.normalise_prefix("") == ""
            assert store.normalise_prefix("/") == "/"
            assert store.normalise_prefix("/somewhere/") == "/somewhere/"
            assert store.normalise_prefix("/somewhere") == "/somewhere/"

        it "can ensure no trailing slash if desired":
            store = Store()
            normalise = lambda prefix: store.normalise_prefix(prefix, trailing_slash=False)
            assert normalise("") == ""
            assert normalise("/") == ""
            assert normalise("/somewhere/") == "/somewhere"
            assert normalise("/somewhere//") == "/somewhere"
            assert normalise("/somewhere") == "/somewhere"

    describe "normalise_path":
        it "uses default_path if path is None":
            default_path = f"/{str(uuid.uuid1())}"
            store = Store(default_path=default_path)
            assert store.normalise_path(None) == default_path

        it "strips leading slashes from the path":
            store = Store()
            assert store.normalise_path("/blah///") == "/blah"
            assert store.normalise_path("/blah") == "/blah"

        it "ensures a first slash":
            store = Store()
            assert store.normalise_path("blah") == "/blah"

        it "passes through otherwise":
            store = Store()
            assert store.normalise_path("/one/two") == "/one/two"

    describe "merge":
        it "takes in the paths from another store":
            one = mock.Mock(name="one")
            two = mock.Mock(name="two")
            three = mock.Mock(name="three")
            four = mock.Mock(name="four")
            five = mock.Mock(name="five")
            six = mock.Mock(name="six")

            store1 = Store()
            store1.paths["/v1"]["/one"] = one
            store1.paths["/v1"]["/two"] = two
            store1.paths["/v2"]["/three"] = three

            store2 = Store()
            store2.paths["/v1"]["/four"] = four
            store2.paths["/v3"]["/five"] = five
            store2.paths["/v1"]["/two"] = six

            store1.merge(store2)
            assert dict(store1.paths) == {
                "/v1": {"/one": one, "/two": six, "/four": four},
                "/v2": {"/three": three},
                "/v3": {"/five": five},
            }

        it "can give a prefix to the merged paths":
            one = mock.Mock(name="one")
            two = mock.Mock(name="two")
            three = mock.Mock(name="three")
            four = mock.Mock(name="four")
            five = mock.Mock(name="five")
            six = mock.Mock(name="six")

            store1 = Store()
            store1.paths["/v1"]["one"] = one
            store1.paths["/v1"]["two"] = two
            store1.paths["/v2"]["three"] = three

            store2 = Store()
            store2.paths["/v1"]["four"] = four
            store2.paths["/v3"]["five"] = five
            store2.paths["/v1"]["two"] = six

            store1.merge(store2, prefix="hello")
            assert dict(store1.paths) == {
                "/v1": {"one": one, "two": two, "hello/two": six, "hello/four": four},
                "/v2": {"three": three},
                "/v3": {"hello/five": five},
            }

    describe "command decorator":
        it "uses the formatter given to the store":
            store = Store(formatter=MergedOptionStringFormatter)

            @store.command("thing", path="/v1")
            class Thing(store.Command):
                one = dictobj.Field(sb.integer_spec)
                two = dictobj.Field(sb.string_spec)
                three = dictobj.Field(sb.overridden("{wat}"), formatted=True)

            wat = mock.Mock(name="wat")
            meta = Meta({"wat": wat}, []).at("options")
            thing = store.paths["/v1"]["thing"]["spec"].normalise(meta, {"one": 2, "two": "yeap"})
            assert thing == {"one": 2, "two": "yeap", "three": wat}

        it "complains if you try to reuse a command":
            store = Store()

            @store.command("thing")
            class Thing(store.Command):
                pass

            # Can use a child kls
            @store.command("another_path")
            class Other(Thing):
                pass

            # Can't use the same class though
            with assertRaises(CantReuseCommands):
                try:
                    store.command("another_path")(Thing)
                except CantReuseCommands as error:
                    assert error.reusing is Thing
                    raise

        it "works":
            store = Store()

            @store.command("thing", path="/v1")
            class Thing(store.Command):
                one = dictobj.Field(sb.integer_spec)
                two = dictobj.Field(sb.string_spec)

            class Spec1:
                def __eq__(s, other):
                    normalised = other.empty_normalise(one=3, two="two")
                    assert isinstance(normalised, Thing)
                    assert normalised == {"one": 3, "two": "two"}
                    return True

            assert dict(store.paths) == {"/v1": {"thing": {"kls": Thing, "spec": Spec1()}}}

            @store.command("one/other", path="/v1")
            class Other(store.Command):
                three = dictobj.Field(sb.integer_spec)
                four = dictobj.Field(sb.boolean)

            class Spec2:
                def __eq__(s, other):
                    normalised = other.empty_normalise(three=5, four=True)
                    assert isinstance(normalised, Other)
                    assert normalised == {"three": 5, "four": True}
                    return True

            assert dict(store.paths) == {
                "/v1": {
                    "thing": {"kls": Thing, "spec": Spec1()},
                    "one/other": {"kls": Other, "spec": Spec2()},
                }
            }

            @store.command("stuff", path="/v2")
            class Stuff(store.Command):
                five = dictobj.Field(sb.string_spec)
                six = dictobj.Field(sb.boolean)

            class Spec3:
                def __eq__(s, other):
                    normalised = other.empty_normalise(five="5", six=False)
                    assert isinstance(normalised, Stuff)
                    assert normalised == {"five": "5", "six": False}
                    return True

            assert dict(store.paths) == {
                "/v1": {
                    "thing": {"kls": Thing, "spec": Spec1()},
                    "one/other": {"kls": Other, "spec": Spec2()},
                },
                "/v2": {"stuff": {"kls": Stuff, "spec": Spec3()}},
            }

            for kls in (Thing, Other, Stuff):
                assert kls.__whirlwind_command__
                assert not kls.__whirlwind_ws_only__

        it "works with interactive commands":
            store = Store()

            class Spec:
                def __init__(s, kls):
                    s.kls = kls

                def __eq__(s, other):
                    s.normalised = other.empty_normalise()
                    assert isinstance(s.normalised, s.kls)
                    assert s.normalised == {}
                    return True

            @store.command("interactive1")
            class Interactive1(store.Command):
                def execute(self, messages):
                    pass

            @store.command("interactive2", parent=Interactive1)
            class Interactive2(store.Command):
                def execute(self, messages):
                    pass

            @store.command("command1", parent=Interactive1)
            class Command1(store.Command):
                pass

            @store.command("command2", parent=Interactive2)
            class Command2(store.Command):
                pass

            got = dict(store.paths)
            want = {
                "/v1": {
                    "interactive1": {"kls": Interactive1, "spec": Spec(Interactive1)},
                    "interactive1:interactive2": {"kls": Interactive2, "spec": Spec(Interactive2)},
                    "interactive1:interactive2:command2": {"kls": Command2, "spec": Spec(Command2)},
                    "interactive1:command1": {"kls": Command1, "spec": Spec(Command1)},
                },
            }

            assert got == want

            for kls in (Interactive1, Interactive2, Command1, Command2):
                assert kls.__whirlwind_command__
                assert kls.__whirlwind_ws_only__

        it "complains if can't find the parent":
            store = Store()

            class W:
                def execute(self, messages):
                    pass

            with assertRaises(NoSuchParent, "Couldn't find parent specified by command: W"):

                @store.command("command", parent=W)
                class Command(store.Command):
                    pass

        it "complains if parent is not interactive":
            store = Store()

            class W:
                def execute(self):
                    pass

            with assertRaises(
                NonInteractiveParent, "Store commands can only specify an interactive parent: W"
            ):

                @store.command("command", parent=W)
                class Command(store.Command):
                    pass

            class W:
                pass

            with assertRaises(
                NonInteractiveParent, "Store commands can only specify an interactive parent: W"
            ):

                @store.command("command", parent=W)
                class Command2(store.Command):
                    pass


describe "command_spec":
    async it "normalises args into a function that makes the command and provides a function for execution":
        store = Store(default_path="/v1", formatter=MergedOptionStringFormatter)

        wat = mock.Mock(name="wat")
        meta = Meta({"wat": wat}, [])

        @store.command("thing")
        class Thing(store.Command):
            one = dictobj.Field(sb.integer_spec)

            async def execute(self):
                return self

        @store.command("other")
        class Other(store.Command):
            two = dictobj.Field(sb.string_spec, wrapper=sb.required)

            async def execute(self):
                return self

        @store.command("stuff", path="/v2")
        class Stuff(store.Command):
            three = dictobj.Field(sb.overridden("{wat}"), formatted=True)

            async def execute(self):
                return self

        thing = await store.command_spec.normalise(
            meta, {"path": "/v1", "body": {"command": "thing", "args": {"one": 20}}}
        )()
        assert thing == {"one": 20}
        assert isinstance(thing, Thing)

        try:
            await store.command_spec.normalise(
                meta, {"path": "/v1", "body": {"command": "other"}}
            )()
            assert False, "expected an error"
        except BadSpecValue as error:
            assert len(error.errors) == 1
            assert error.errors[0].as_dict() == {
                "message": "Bad value. Expected a value but got none",
                "meta": meta.at("body").at("args").at("two").delfick_error_format("two"),
            }

        stuff = await store.command_spec.normalise(
            meta, {"path": "/v2", "body": {"command": "stuff"}}
        )()
        assert stuff == {"three": wat}
        assert isinstance(stuff, Stuff)

        assert len(store.command_spec.existing_commands) == 0

    async it "doesn't allow ws_only commands if told not to":
        store = Store(default_path="/v1", formatter=MergedOptionStringFormatter)

        @store.command("interactive")
        class Interactive(store.Command):
            async def execute(self, messages):
                pass

        @store.command("command1", parent=Interactive)
        class Command1(store.Command):
            async def execute(self):
                pass

        @store.command("command2")
        class Command2(store.Command):
            async def execute(self):
                pass

        @store.command("command3")
        class Command3(store.Command):
            async def execute(self):
                pass

        final_future = asyncio.Future()
        message_id = str(uuid.uuid1())
        meta = Meta(
            {
                "message_id": message_id,
                "final_future": final_future,
            },
            [],
        )

        with assertRaises(
            BadSpecValue,
            "Unknown command",
            available=["command2", "command3"],
            wanted="nonexistant",
            meta=meta.at("body").at("command"),
        ):
            store.command_spec.normalise(meta, {"path": "/v1", "body": {"command": "nonexistant"}})

        with assertRaises(
            BadSpecValue,
            "Unknown command",
            available=["command2", "command3", "interactive", "interactive:command1"],
            wanted="nonexistant",
            meta=meta.at("body").at("command"),
        ):
            store.command_spec.normalise(
                meta, {"path": "/v1", "body": {"command": "nonexistant"}, "allow_ws_only": True}
            )

        with assertRaises(
            BadSpecValue,
            "Command is for websockets only",
            available=["command2", "command3"],
            meta=meta.at("body").at("command"),
        ):
            store.command_spec.normalise(meta, {"path": "/v1", "body": {"command": "interactive"}})

    async it "allows children commands":
        store = Store(default_path="/v1", formatter=MergedOptionStringFormatter)

        thing_started = asyncio.Future()
        another_started = asyncio.Future()

        runners = [asyncio.Future()]
        final_future = asyncio.Future()
        request_future = asyncio.Future()

        def progress_cb(msg, **kwargs):
            if isinstance(msg, Exception):
                runners[0].set_exception(msg)
                return

            if msg["instruction"] == "thing_started":
                thing_started.set_result(True)
            elif msg["instruction"] == "another_started":
                another_started.set_result(True)

        def make_meta(message_id, **kwargs):
            return Meta(
                {
                    "message_id": message_id,
                    "final_future": final_future,
                    "request_future": request_future,
                    "progress_cb": progress_cb,
                    **kwargs,
                },
                [],
            )

        @store.command("thing")
        class Thing(store.Command):
            one = dictobj.Field(sb.integer_spec)
            progress_cb = store.injected("progress_cb")

            async def execute(self, messages):
                self.progress_cb({"instruction": "thing_started"})

                async for message in messages:
                    task = message.process()
                    if task.done() and task.exception():
                        self.progress_cb(task.exception())
                        continue

                    if not message.interactive:
                        await task

                    if isinstance(message.command, Other) and message.command.instruction == "stop":
                        break

        @store.command("other", parent=Thing)
        class Other(store.Command):
            parent = store.injected("_parent_command")

            instruction = dictobj.Field(sb.string_spec, wrapper=sb.required)

            async def execute(self):
                return self, self.parent

        @store.command("another", parent=Thing)
        class AnotherInteractive(store.Command):
            progress_cb = store.injected("progress_cb")

            async def execute(self, messages):
                self.progress_cb({"instruction": "another_started"})

                ts = []
                async for message in messages:
                    t = message.process()
                    if t.done() and t.exception():
                        await t
                    ts.append(t)
                    if len(ts) == 2:
                        break

                got = []
                for t in ts:
                    got.append(await t)
                return got

        @store.command("amaze", parent=AnotherInteractive)
        class Amaze(store.Command):
            number = dictobj.Field(sb.integer_spec)

            async def execute(self):
                return self.number

        parent_message_id = str(uuid.uuid1())

        child1_message_id = str(uuid.uuid1())
        child2_message_id = str(uuid.uuid1())
        child3_message_id = str(uuid.uuid1())

        grandchild1_message_id = str(uuid.uuid1())
        grandchild2_message_id = str(uuid.uuid1())

        def add_runner(name, coro):
            task = create_task(coro, name=name)
            runners.append(task)
            return task

        thing_task = add_runner(
            "start_thing",
            store.command_spec.normalise(
                make_meta(parent_message_id),
                {
                    "path": "/v1",
                    "body": {"command": "thing", "args": {"one": 2}},
                    "allow_ws_only": True,
                },
            )(),
        )

        async def wait_for(name, fut):
            await asyncio.wait([fut, *runners], return_when=asyncio.FIRST_COMPLETED)

            for t in runners:
                if t.done() and not t.cancelled():
                    await t

            for t in runners:
                if t.done():
                    await t

            return await fut

        try:
            await wait_for("wait for started thing", thing_started)

            thing = await store.command_spec.normalise(
                make_meta((parent_message_id, child1_message_id)),
                {
                    "path": "/v1",
                    "body": {"command": "other", "args": {"instruction": "nothing"}},
                    "allow_ws_only": True,
                },
            )()
            parent1 = thing[1]
            assert thing == (
                {"instruction": "nothing", "parent": parent1},
                {"one": 2, "progress_cb": progress_cb},
            )
            assert isinstance(parent1, Thing)
            assert isinstance(thing[0], Other)

            another_task = add_runner(
                "start_another",
                store.command_spec.normalise(
                    make_meta((parent_message_id, child3_message_id)),
                    {"path": "/v1", "body": {"command": "another"}, "allow_ws_only": True},
                )(),
            )

            await wait_for("wait for another to start", another_started)

            t1 = await store.command_spec.normalise(
                make_meta((parent_message_id, child3_message_id, grandchild1_message_id)),
                {
                    "path": "/v1",
                    "body": {"command": "amaze", "args": {"number": 23}},
                    "allow_ws_only": True,
                },
            )()

            t2 = await store.command_spec.normalise(
                make_meta((parent_message_id, child3_message_id, grandchild2_message_id)),
                {
                    "path": "/v1",
                    "body": {"command": "amaze", "args": {"number": 42}},
                    "allow_ws_only": True,
                },
            )()

            thing = await another_task
            assert thing == [23, 42]

            assert t1 == 23
            assert t2 == 42

            thing2 = await store.command_spec.normalise(
                make_meta((parent_message_id, child2_message_id)),
                {
                    "path": "/v1",
                    "body": {"command": "other", "args": {"instruction": "stop"}},
                    "allow_ws_only": True,
                },
            )()
            parent2 = thing2[1]
            assert thing2 == (
                {"instruction": "stop", "parent": parent2},
                {"one": 2, "progress_cb": progress_cb},
            )
            assert isinstance(parent1, Thing)
            assert parent1 is parent2
            assert isinstance(thing2[0], Other)

            assert (await thing_task) is None
        finally:
            final_future.cancel()

            for t in runners:
                t.cancel()

            if runners:
                await asyncio.wait(runners)

    it "complains if the path or command is unknown":
        store = Store(default_path="/v1")
        meta = Meta({}, [])

        try:
            store.command_spec.normalise(meta, {"path": "/somewhere", "body": {"command": "thing"}})
            assert False, "Expected an error"
        except NoSuchPath as error:
            assert error.wanted == "/somewhere"
            assert error.available == []

        @store.command("thing")
        class Thing(store.Command):
            pass

        @store.command("other")
        class Other(store.Command):
            pass

        @store.command("stuff", path="/v2")
        class Stuff(store.Command):
            pass

        try:
            store.command_spec.normalise(meta, {"path": "/somewhere", "body": {"command": "thing"}})
            assert False, "Expected an error"
        except NoSuchPath as error:
            assert error.wanted == "/somewhere"
            assert error.available == ["/v1", "/v2"]

        try:
            store.command_spec.normalise(meta, {"path": "/v1", "body": {"command": "missing"}})
            assert False, "Expected an error"
        except BadSpecValue as error:
            assert error.as_dict() == {
                "message": "Bad value. Unknown command",
                "wanted": "missing",
                "available": ["other", "thing"],
                "meta": meta.at("body").at("command").delfick_error_format("command"),
            }
