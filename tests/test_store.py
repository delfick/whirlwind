# coding: spec

from whirlwind.store import Store

from option_merge.formatter import MergedOptionStringFormatter
from input_algorithms.errors import BadSpecValue
from input_algorithms.dictobj import dictobj
from input_algorithms import spec_base as sb
from input_algorithms.meta import Meta
from unittest import TestCase, mock
import uuid

describe TestCase, "Store":
    it "takes in some things":
        prefix = mock.Mock(name="prefix")
        formatter = mock.Mock(name="formatter")
        default_path = mock.Mock(name="default_path")

        store = Store(prefix=prefix, default_path=default_path, formatter=formatter)

        self.assertIs(store.prefix, prefix)
        self.assertIs(store.default_path, default_path)
        self.assertIs(store.formatter, formatter)

        self.assertEqual(dict(store.paths), {})

    it "has defaults":
        store = Store()

        self.assertEqual(store.prefix, "")
        self.assertEqual(store.default_path, "/v1")
        self.assertIs(store.formatter, None)

    it "normalises the prefix":
        store = Store(prefix="/somewhere/nice")
        self.assertEqual(store.prefix, "/somewhere/nice/")

    describe "normalise_prefix":
        it "says None is an empty string":
            store = Store()
            self.assertEqual(store.normalise_prefix(None), "")

        it "ensures a trailing slash when we have a prefix":
            store = Store()
            self.assertEqual(store.normalise_prefix(""), "")
            self.assertEqual(store.normalise_prefix("/"), "/")
            self.assertEqual(store.normalise_prefix("/somewhere/"), "/somewhere/")
            self.assertEqual(store.normalise_prefix("/somewhere"), "/somewhere/")

        it "can ensure no trailing slash if desired":
            store = Store()
            normalise = lambda prefix: store.normalise_prefix(prefix, trailing_slash=False)
            self.assertEqual(normalise(""), "")
            self.assertEqual(normalise("/"), "")
            self.assertEqual(normalise("/somewhere/"), "/somewhere")
            self.assertEqual(normalise("/somewhere//"), "/somewhere")
            self.assertEqual(normalise("/somewhere"), "/somewhere")

    describe "normalise_path":
        it "uses default_path if path is None":
            default_path = f"/{str(uuid.uuid1())}"
            store = Store(default_path=default_path)
            self.assertEqual(store.normalise_path(None), default_path)

        it "strips leading slashes from the path":
            store = Store()
            self.assertEqual(store.normalise_path("/blah///"), "/blah")
            self.assertEqual(store.normalise_path("/blah"), "/blah")

        it "ensures a first slash":
            store = Store()
            self.assertEqual(store.normalise_path("blah"), "/blah")

        it "passes through otherwise":
            store = Store()
            self.assertEqual(store.normalise_path("/one/two"), "/one/two")

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
            self.assertEqual(dict(store1.paths)
                , { "/v1":
                    { "/one": one
                    , "/two": six
                    , "/four": four
                    }
                  , "/v2":
                    { "/three": three
                    }
                  , "/v3":
                    { "/five": five
                    }
                  }
                )

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
            self.assertEqual(dict(store1.paths)
                , { "/v1":
                    { "one": one
                    , "two": two
                    , "hello/two": six
                    , "hello/four": four
                    }
                  , "/v2":
                    { "three": three
                    }
                  , "/v3":
                    { "hello/five": five
                    }
                  }
                )

    describe "command decorator":
        it "uses the formatter given to the store":
            class Formatter(MergedOptionStringFormatter):
                def special_get_field(self, *args, **kwargs):
                    pass

                def special_format_field(self, *args, **kwargs):
                    pass

            store = Store(formatter=Formatter)

            @store.command("thing", path="/v1")
            class Thing(dictobj.Spec):
                one = dictobj.Field(sb.integer_spec)
                two = dictobj.Field(sb.string_spec)
                three = dictobj.Field(sb.overridden("{wat}"), formatted=True)

            wat = mock.Mock(name="wat")
            meta = Meta({"wat": wat}, []).at("options")
            thing = store.paths["/v1"]["thing"]["spec"].normalise(meta, {"one": 2, "two": "yeap"})
            self.assertEqual(thing, {"one": 2, "two": "yeap", "three": wat})

        it "works":
            store = Store()

            @store.command("thing", path="/v1")
            class Thing(dictobj.Spec):
                one = dictobj.Field(sb.integer_spec)
                two = dictobj.Field(sb.string_spec)

            class Spec1:
                def __eq__(s, other):
                    normalised = other.empty_normalise(one=3, two="two")
                    self.assertIsInstance(normalised, Thing)
                    self.assertEqual(normalised, {"one": 3, "two": "two"})
                    return True

            self.assertEqual(dict(store.paths),
                  { "/v1":
                    { "thing": {"kls": Thing, "spec": Spec1()}
                    }
                  }
                )

            @store.command("one/other", path="/v1")
            class Other(dictobj.Spec):
                three = dictobj.Field(sb.integer_spec)
                four = dictobj.Field(sb.boolean)

            class Spec2:
                def __eq__(s, other):
                    normalised = other.empty_normalise(three=5, four=True)
                    self.assertIsInstance(normalised, Other)
                    self.assertEqual(normalised, {"three": 5, "four": True})
                    return True

            self.assertEqual(dict(store.paths),
                  { "/v1":
                    { "thing": {"kls": Thing, "spec": Spec1()}
                    , "one/other": {"kls": Other, "spec": Spec2()}
                    }
                  }
                )

            @store.command("stuff", path="/v2")
            class Stuff(dictobj.Spec):
                five = dictobj.Field(sb.string_spec)
                six = dictobj.Field(sb.boolean)

            class Spec3:
                def __eq__(s, other):
                    normalised = other.empty_normalise(five="5", six=False)
                    self.assertIsInstance(normalised, Stuff)
                    self.assertEqual(normalised, {"five": "5", "six": False})
                    return True

            self.assertEqual(dict(store.paths),
                  { "/v1":
                    { "thing": {"kls": Thing, "spec": Spec1()}
                    , "one/other": {"kls": Other, "spec": Spec2()}
                    }
                  , "/v2":
                    { "stuff": {"kls": Stuff, "spec": Spec3()}
                    }
                  }
                )

            assert Thing.__whirlwind_command__
            assert Other.__whirlwind_command__
            assert Stuff.__whirlwind_command__

    describe "command_spec":
        it "normalises args into the spec for the correct object":
            class Formatter(MergedOptionStringFormatter):
                def special_get_field(self, *args, **kwargs):
                    pass

                def special_format_field(self, *args, **kwargs):
                    pass

            store = Store(default_path="/v1", formatter=Formatter)

            wat = mock.Mock(name="wat")
            meta = Meta({"wat": wat}, [])

            @store.command("thing")
            class Thing(dictobj.Spec):
                one = dictobj.Field(sb.integer_spec)

            @store.command("other")
            class Other(dictobj.Spec):
                two = dictobj.Field(sb.string_spec, wrapper=sb.required)

            @store.command("stuff", path="/v2")
            class Stuff(dictobj.Spec):
                three = dictobj.Field(sb.overridden("{wat}"), formatted=True)

            thing = store.command_spec.normalise(meta
                , {"path": "/v1", "body": {"command": "thing", "args": {"one": 20}}}
                )
            self.assertEqual(thing, {"one": 20})
            self.assertIsInstance(thing, Thing)

            try:
                store.command_spec.normalise(meta
                    , {"path": "/v1", "body": {"command": "other"}}
                    )
                assert False, "expected an error"
            except BadSpecValue as error:
                self.assertEqual(len(error.errors), 1)
                self.assertEqual(error.errors[0].as_dict()
                    , { "message": "Bad value. Expected a value but got none"
                      , "meta": meta.at("body").at("args").at("two").delfick_error_format("two")
                      }
                    )

            stuff = store.command_spec.normalise(meta
                , {"path": "/v2", "body": {"command": "stuff"}}
                )
            self.assertEqual(stuff, {"three": wat})
            self.assertIsInstance(stuff, Stuff)

        it "complains if the path or command is unknown":
            store = Store(default_path="/v1")
            meta = Meta({}, [])

            try:
                store.command_spec.normalise(meta, {"path": "/somewhere", "body": {"command": "thing"}})
                assert False, "Expected an error"
            except BadSpecValue as error:
                self.assertEqual(error.as_dict()
                    , { "message": "Bad value. Unknown path"
                      , "wanted": "/somewhere"
                      , "available": []
                      , "meta": meta.at("path").delfick_error_format("meta")
                      }
                    )

            @store.command("thing")
            class Thing(dictobj.Spec):
                pass

            @store.command("other")
            class Other(dictobj.Spec):
                pass

            @store.command("stuff", path="/v2")
            class Stuff(dictobj.Spec):
                pass

            try:
                store.command_spec.normalise(meta, {"path": "/somewhere", "body": {"command": "thing"}})
                assert False, "Expected an error"
            except BadSpecValue as error:
                self.assertEqual(error.as_dict()
                    , { "message": "Bad value. Unknown path"
                      , "wanted": "/somewhere"
                      , "available": ["/v1", "/v2"]
                      , "meta": meta.at("path").delfick_error_format("meta")
                      }
                    )

            try:
                store.command_spec.normalise(meta, {"path": "/v1", "body": {"command": "missing"}})
                assert False, "Expected an error"
            except BadSpecValue as error:
                self.assertEqual(error.as_dict()
                    , { "message": "Bad value. Unknown command"
                      , "wanted": "missing"
                      , "available": ["other", "thing"]
                      , "meta": meta.at("body").at("command").delfick_error_format("command")
                      }
                    )
