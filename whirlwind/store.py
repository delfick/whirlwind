from whirlwind.commander import Command

from delfick_project.norms import dictobj, sb, BadSpecValue
from delfick_project.option_merge import NoFormat
from collections import defaultdict
import inspect


def is_interactive(obj):
    return (
        obj and hasattr(obj, "execute") and "messages" in inspect.signature(obj.execute).parameters
    )


class NoSuchPath(Exception):
    def __init__(self, wanted, available):
        self.wanted = wanted
        self.available = available


class NoSuchParent(Exception):
    def __init__(self, wanted):
        self.wanted = wanted

        s = repr(self.wanted)
        if hasattr(self.wanted, "__name__"):
            s = self.wanted.__name__

        super().__init__(self, f"Couldn't find parent specified by command: {s}")


class NonInteractiveParent(Exception):
    def __init__(self, wanted):
        self.wanted = wanted

        s = repr(self.wanted)
        if hasattr(self.wanted, "__name__"):
            s = self.wanted.__name__

        super().__init__(self, f"Store commands can only specify an interactive parent: {s}")


class Store:
    Command = Command

    _merged_options_formattable = True

    def __init__(self, prefix=None, default_path="/v1", formatter=None):
        self.prefix = self.normalise_prefix(prefix)
        self.formatter = formatter
        self.default_path = default_path
        self.paths = defaultdict(dict)

    def clone(self):
        new_store = Store(self.prefix, self.default_path, self.formatter)
        for path, commands in self.paths.items():
            new_store.paths[path].update(dict(commands))
        return new_store

    def injected(self, path, format_into=sb.NotSpecified, nullable=False):
        class find_value(sb.Spec):
            def normalise(s, meta, val):
                if nullable and path not in meta.everything:
                    return NoFormat(None)
                return f"{{{path}}}"

        return dictobj.Field(find_value(), formatted=True, format_into=format_into)

    def normalise_prefix(self, prefix, trailing_slash=True):
        if prefix is None:
            return ""

        if trailing_slash:
            if prefix and not prefix.endswith("/"):
                return f"{prefix}/"
        else:
            while prefix and prefix.endswith("/"):
                prefix = prefix[:-1]

        return prefix

    def normalise_path(self, path):
        if path is None:
            path = self.default_path

        while path and path.endswith("/"):
            path = path[:-1]

        if not path.startswith("/"):
            path = f"/{path}"

        return path

    def merge(self, other, prefix=None):
        new_prefix = self.normalise_prefix(prefix, trailing_slash=False)
        for path, commands in other.paths.items():
            for name, options in commands.items():
                slash = ""
                if not new_prefix.endswith("/") and not name.startswith("/"):
                    slash = "/"
                self.paths[path][f"{new_prefix}{slash}{name}"] = options

    def command(self, name, *, path=None, parent=None):
        path = self.normalise_path(path)

        def decorator(kls):
            kls.__whirlwind_command__ = True
            kls.__whirlwind_ws_only__ = is_interactive(kls) or parent

            n = name
            spec = kls.FieldSpec(formatter=self.formatter)

            if parent and not is_interactive(parent):
                raise NonInteractiveParent(parent)
            elif parent:
                found = False
                for p, o in self.paths[path].items():
                    if o["kls"] is parent:
                        n = f"{p}:{name}"
                        found = True
                        break

                if not found:
                    raise NoSuchParent(parent)
            else:
                n = f"{self.prefix}{n}"

            self.paths[path][n] = {"kls": kls, "spec": spec}
            return kls

        return decorator

    @property
    def command_spec(self):
        class command_spec(sb.Spec):
            """
            Knows how to turn ``{"path": <string>, "body": {"command": <string>, "args": <dict>}}``
            into a Command object.

            It uses the FieldSpec in self.paths to normalise the args into
            the Command instance.
            """

            def normalise_filled(s, meta, val):
                v = sb.set_options(path=sb.required(sb.string_spec())).normalise(meta, val)

                path = v["path"]

                if path not in self.paths:
                    raise NoSuchPath(path, sorted(self.paths))

                val = sb.set_options(
                    body=sb.required(
                        sb.set_options(
                            args=sb.dictionary_spec(), command=sb.required(sb.string_spec())
                        )
                    )
                ).normalise(meta, val)

                args = val["body"]["args"]
                name = val["body"]["command"]

                available_commands = self.paths[path]

                if name not in available_commands:
                    raise BadSpecValue(
                        "Unknown command",
                        wanted=name,
                        available=sorted(available_commands),
                        meta=meta.at("body").at("command"),
                    )

                return available_commands[name]["spec"].normalise(meta.at("body").at("args"), args)

        return command_spec()
