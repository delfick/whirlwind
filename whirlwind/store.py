from input_algorithms.errors import BadSpecValue
from input_algorithms import spec_base as sb
from collections import defaultdict

class Store:
    def __init__(self, prefix=None, default_path="/v1", formatter=None):
        self.prefix = self.normalise_prefix(prefix)
        self.formatter = formatter
        self.default_path = default_path
        self.paths = defaultdict(dict)

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

    def command(self, name, path=None):
        path = self.normalise_path(path)

        def decorator(kls):
            kls.__whirlwind_command__ = True
            spec = kls.FieldSpec(formatter=self.formatter)
            self.paths[path][f"{self.prefix}{name}"] = {"kls": kls, "spec": spec}
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
                val = sb.set_options(
                      path = sb.required(sb.string_spec())
                    , body = sb.required(sb.set_options(
                        args = sb.dictionary_spec()
                      , command = sb.required(sb.string_spec())
                      ))
                    ).normalise(meta, val)

                path = val["path"]
                args = val["body"]["args"]
                name = val["body"]["command"]

                if path not in self.paths:
                    raise BadSpecValue("Unknown path"
                        , wanted=path
                        , available=sorted(self.paths)
                        , meta=meta.at("path")
                        )

                available_commands = self.paths[path]

                if name not in available_commands:
                    raise BadSpecValue("Unknown command"
                        , wanted=name
                        , available=sorted(available_commands)
                        , meta=meta.at("body").at("command")
                        )

                return available_commands[name]["spec"].normalise(meta.at("body").at("args"), args)

        return command_spec()
