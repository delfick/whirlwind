# coding: spec

from whirlwind.store import Store, NoSuchPath

from delfick_project.option_merge import MergedOptionStringFormatter
from delfick_project.norms import dictobj, sb, Meta, BadSpecValue
from unittest import mock
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

            assert Thing.__whirlwind_command__
            assert Other.__whirlwind_command__
            assert Stuff.__whirlwind_command__

    describe "command_spec":
        it "normalises args into the spec for the correct object":
            store = Store(default_path="/v1", formatter=MergedOptionStringFormatter)

            wat = mock.Mock(name="wat")
            meta = Meta({"wat": wat}, [])

            @store.command("thing")
            class Thing(store.Command):
                one = dictobj.Field(sb.integer_spec)

            @store.command("other")
            class Other(store.Command):
                two = dictobj.Field(sb.string_spec, wrapper=sb.required)

            @store.command("stuff", path="/v2")
            class Stuff(store.Command):
                three = dictobj.Field(sb.overridden("{wat}"), formatted=True)

            thing = store.command_spec.normalise(
                meta, {"path": "/v1", "body": {"command": "thing", "args": {"one": 20}}}
            )
            assert thing == {"one": 20}
            assert isinstance(thing, Thing)

            try:
                store.command_spec.normalise(meta, {"path": "/v1", "body": {"command": "other"}})
                assert False, "expected an error"
            except BadSpecValue as error:
                assert len(error.errors) == 1
                assert error.errors[0].as_dict() == {
                    "message": "Bad value. Expected a value but got none",
                    "meta": meta.at("body").at("args").at("two").delfick_error_format("two"),
                }

            stuff = store.command_spec.normalise(
                meta, {"path": "/v2", "body": {"command": "stuff"}}
            )
            assert stuff == {"three": wat}
            assert isinstance(stuff, Stuff)

        it "complains if the path or command is unknown":
            store = Store(default_path="/v1")
            meta = Meta({}, [])

            try:
                store.command_spec.normalise(
                    meta, {"path": "/somewhere", "body": {"command": "thing"}}
                )
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
                store.command_spec.normalise(
                    meta, {"path": "/somewhere", "body": {"command": "thing"}}
                )
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
