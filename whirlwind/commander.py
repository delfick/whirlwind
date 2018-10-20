from input_algorithms.dictobj import dictobj
from option_merge import MergedOptions
from input_algorithms.meta import Meta
import asyncio

class Command(dictobj.Spec):
    async def execute(self):
        raise NotImplementedError("Base command has no execute implementation")

class Commander:
    """
    Entry point for creating an executor to execute commands with
    """
    _merged_options_formattable = True

    def __init__(self, store, **options):
        self.store = store

        everything = MergedOptions.using(
              options
            , {"commander": self}
            , dont_prefix = [dictobj]
            )

        self.meta = Meta(everything, [])

    def process_reply(self, msg, exc_info):
        """Hook for every reply and progress message sent to the client"""

    def executor(self, progress_cb, request_handler, **extra_options):
        return Executor(self, progress_cb, request_handler, extra_options)

class Executor:
    _merged_options_formattable = True

    def __init__(self, commander, progress_cb, request_handler, extra_options):
        self.commander = commander
        self.progress_cb = progress_cb
        self.extra_options = extra_options
        self.request_handler = request_handler

    async def execute(self, path, body, extra_options=None):
        """
        Responsible for creating a command and calling execute on it.

        If command is not already a Command instance then we normalise it
        into one.

        We have available on the meta object:

        __init__ options
            Anything that is provided to the Commander and Executor at __init__

        store
            The store of commands

        path
            The path that was passed in

        executor
            This executor

        request_future
            A future that is cancelled after execute is finished

        extra options
            Anything provided as extra_options to this function
        """
        request_future = asyncio.Future()
        request_future._merged_options_formattable = True

        try:
            everything = MergedOptions.using(
                  self.commander.meta.everything
                , { "path": path
                  , "store": self.commander.store
                  , "executor": self
                  , "progress_cb": self.progress_cb
                  , "request_future": request_future
                  , "request_handler": self.request_handler
                  }
                , self.extra_options
                , extra_options or {}
                , dont_prefix = [dictobj]
                )

            meta = Meta(everything, self.commander.meta.path).at("<input>")
            command = self.commander.store.command_spec.normalise(meta, {"path": path, "body": body})

            return await command.execute()
        finally:
            request_future.cancel()
