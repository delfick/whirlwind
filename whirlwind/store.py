from whirlwind.commander import Command

from delfick_project.norms import dictobj, sb, BadSpecValue, Meta
from delfick_project.option_merge import NoFormat, MergedOptions
from collections import defaultdict
from textwrap import dedent
import logging
import asyncio
import inspect
import sys


log = logging.getLogger("whirlwind.store")


class CantReuseCommands(Exception):
    def __init__(self, reusing):
        self.reusing = reusing
        super().__init__(
            dedent(
                f"""
            You tried to reuse {self.reusing} as a store command.

            You can use a subclass instead. For example:

                @store.command("command")
                class Example(store.Command):
                    ...

                @store.command("command2")
                class Example2(Example):
                    ...

            Or you can do something like:

                class Base(store.Command):
                    ...

                @store.command("command1")
                class Command1(Base):
                    ...

                @store.command("command2")
                class Command2(Base):
                    ...
        """
            )
        )


def create_task(coro, name=None):
    loop = asyncio.get_event_loop()
    version_info = sys.version_info
    if version_info >= (3, 8):
        return loop.create_task(coro, name=name)
    elif version_info >= (3, 7):
        return loop.create_task(coro)
    else:
        return asyncio.ensure_future(coro)


def retrieve_exception(result):
    if result.cancelled():
        return
    result.exception()


def is_interactive(obj):
    return (
        obj and hasattr(obj, "execute") and "messages" in inspect.signature(obj.execute).parameters
    )


async def pass_on_result(fut, command, execute, *, log_exceptions):
    if execute:
        coro = execute()
    else:
        coro = command.execute()

    def transfer(result):
        if result.cancelled():
            fut.cancel()
            return

        exc = result.exception()
        if fut.done():
            return

        if exc:
            if log_exceptions:
                log.error(exc)
            fut.set_exception(exc)
        else:
            fut.set_result(result.result())

    task = create_task(coro, name=f"<pass_on_result: {command.__class__.__name__}>")
    task.add_done_callback(transfer)
    return await fut


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


class ProcessItem:
    def __init__(self, fut, command, execute, messages):
        self.fut = fut
        self.execute = execute
        self.command = command
        self.messages = messages
        self.interactive = is_interactive(self.command)

    def process(self):
        try:
            coro = pass_on_result(
                self.fut, self.command, self.execute, log_exceptions=self.interactive
            )
        except:
            self.fut.set_exception(sys.exc_info()[1])
            return self.fut
        else:
            task = create_task(coro, name=f"<process: {self.command.__class__.__name__}>")
            task.add_done_callback(retrieve_exception)
            self.messages.ts.append((task, False, True))

            return task

    def no_process(self):
        self.fut.set_result({"received": True})
        return self.fut


class MessageHolder:
    def __init__(self, command, final_future):
        self.ts = []
        self.command = command
        self.queue = asyncio.Queue()
        self.final_future = final_future

    def add_main_task(self, main_task):
        self.main_task = main_task

    async def finish(self, cancelled=False):
        exception = None
        if hasattr(self, "main_task") and self.main_task.done():
            if self.main_task.cancelled():
                cancelled = True
            elif self.main_task.exception():
                exception = self.main_task.exception()

        if self.ts:
            for t, do_cancel, do_transfer in self.ts:
                if do_transfer and exception and not t.done():
                    t.set_exception(exception)
                if cancelled or do_cancel:
                    t.cancel()
            await asyncio.wait([t for t, _, _ in self.ts])

    async def add(self, fut, command, execute=None):
        fut.add_done_callback(retrieve_exception)
        self.ts.append((fut, False, True))

        await self.queue.put(ProcessItem(fut, command, execute, self))

    def __aiter__(self):
        return self

    async def __anext__(self):
        while True:
            getter = create_task(
                self.queue.get(), name=f"<queue.get: {self.command.__class__.__name__}>"
            )
            self.ts.append((getter, True, False))
            await asyncio.wait([getter, self.final_future], return_when=asyncio.FIRST_COMPLETED)
            self.ts = [i for i in self.ts if not i[0].done()]

            if self.final_future.done():
                getter.cancel()
                await asyncio.wait([getter])
                raise StopAsyncIteration

            nxt = await getter
            if nxt is not None:
                return nxt


class command_spec(sb.Spec):
    """
    Knows how to turn ``{"path": <string>, "body": {"command": <string>, "args": <dict>}}``
    into the execute method of a Command object.

    It uses the FieldSpec in self.paths to normalise the args into the Command instance.
    """

    def setup(self, paths):
        self.paths = paths
        self.existing_commands = {}

    def make_command(self, meta, val, existing):
        v = sb.set_options(
            path=sb.required(sb.string_spec()), allow_ws_only=sb.defaulted(sb.boolean(), False)
        ).normalise(meta, val)

        path = v["path"]
        allow_ws_only = v["allow_ws_only"]

        if path not in self.paths:
            raise NoSuchPath(path, sorted(self.paths))

        val = sb.set_options(
            body=sb.required(
                sb.set_options(args=sb.dictionary_spec(), command=sb.required(sb.string_spec()))
            )
        ).normalise(meta, val)

        args = val["body"]["args"]
        name = val["body"]["command"]

        if existing:
            name = val["body"]["command"] = f"{existing['path']}:{name}"

        extra_context = {}
        if existing:
            extra_context["_parent_command"] = existing["command"]

        everything = meta.everything
        if isinstance(meta.everything, MergedOptions):
            everything = meta.everything.wrapped()
        everything.update(extra_context)
        meta = Meta(everything, []).at("body")

        available_commands = self.paths[path]

        if name not in available_commands:
            raise BadSpecValue(
                "Unknown command",
                wanted=name,
                available=self.available(available_commands, allow_ws_only=allow_ws_only),
                meta=meta.at("command"),
            )

        command = available_commands[name]["spec"].normalise(meta.at("args"), args)

        if not allow_ws_only and command.__whirlwind_ws_only__:
            raise BadSpecValue(
                "Command is for websockets only",
                wanted=name,
                available=self.available(available_commands, allow_ws_only=allow_ws_only),
                meta=meta.at("command"),
            )

        return command, name

    def available(self, available_commands, *, allow_ws_only):
        available = []
        for name, info in available_commands.items():
            if allow_ws_only or not info["kls"].__whirlwind_ws_only__:
                available.append(name)

        return sorted(available)

    def find_command(self, message_id):
        if isinstance(message_id, tuple) and len(message_id) == 1:
            message_id = message_id[0]

        if not message_id or isinstance(message_id, str):
            return None, (message_id,)

        parent = message_id[:-1]
        if parent not in self.existing_commands:
            raise NoSuchParent(wanted=parent)

        return self.existing_commands[parent], message_id

    def normalise_filled(self, meta, val):
        parent_existing, message_id_tuple = self.find_command(meta.everything.get("message_id"))
        command, path = self.make_command(meta, val, parent_existing)

        existing = None
        if command and is_interactive(command):
            existing = {"command": command, "messages": None, "path": path}
            self.existing_commands[message_id_tuple] = existing

        async def execute():
            if parent_existing and not existing:
                fut = asyncio.Future()
                await parent_existing["messages"].add(fut, command, ())
                return await fut

            try:
                if not existing:
                    return await command.execute()
                else:
                    request_future = meta.everything.get("request_future")
                    return await self.execute_interactive(
                        request_future, parent_existing, existing, command
                    )
            finally:
                if message_id_tuple in self.existing_commands:
                    del self.existing_commands[message_id_tuple]

        return execute

    async def execute_interactive(self, request_future, parent_existing, existing, command):
        holder_kls = MessageHolder
        if hasattr(command, "MessageHolder"):
            holder_kls = command.MessageHolder
        existing["messages"] = holder_kls(command, request_future)

        async def execute():
            try:
                task = create_task(
                    existing["command"].execute(existing["messages"]),
                    name=f"<execute interactive: {command.__class__.__name__}",
                )
                existing["messages"].add_main_task(task)
                return await task
            finally:
                cancelled = False
                exc_info = sys.exc_info()
                if exc_info and isinstance(exc_info[1], asyncio.CancelledError):
                    cancelled = True

                if isinstance(existing, dict) and existing["messages"]:
                    try:
                        await existing["messages"].finish(cancelled=cancelled)
                    except asyncio.CancelledError:
                        raise
                    except:
                        log.exception("Failed to finish the message holder")

        if parent_existing:
            fut = asyncio.Future()
            await parent_existing["messages"].add(fut, command, execute)
            return await fut
        else:
            return await execute()


class Store:
    Command = Command

    _merged_options_formattable = True

    def __init__(self, prefix=None, default_path="/v1", formatter=None):
        self.prefix = self.normalise_prefix(prefix)
        self.formatter = formatter
        self.default_path = default_path
        self.paths = defaultdict(dict)
        self.command_spec = command_spec(self.paths)

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
            if "__whirlwind_command__" in kls.__dict__:
                raise CantReuseCommands(kls)

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
