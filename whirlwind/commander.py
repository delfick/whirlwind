from input_algorithms.dictobj import dictobj
from option_merge import MergedOptions
from input_algorithms.meta import Meta
import asyncio

class Command(dictobj.Spec):
    async def execute(self):
        raise NotImplementedError("Base command has no execute implementation")

class Commander:
    """
    Entry point to commands.
    """
    _merged_options_formattable = True

    def __init__(self, command_spec, **options):
        self.command_spec = command_spec

        everything = MergedOptions.using(
              options
            , {"commander": self}
            , dont_prefix = [dictobj]
            )

        self.meta = Meta(everything, [])

    def process_reply(self, msg, exc_info):
        """Hook for every reply and progress message sent to the client"""

    async def execute(self, path, body, progress_cb, request_handler, extra_options=None):
        """
        Responsible for creating a command and calling execute on it.

        If command is not already a Command instance then we normalise it
        into one.

        We have available on the meta object:

        __init__ options
            Anything that is provided to the Commander at __init__

        progress_cb
            A callback that takes in a message. This is provided by whatever
            calls execute. It should take a single variable.

        request_future
            A future that is cancelled after execute is finished

        extra options
            Anything provided as extra_options to this function
        """
        request_future = asyncio.Future()
        request_future._merged_options_formattable = True

        try:
            everything = MergedOptions.using(
                  self.meta.everything
                , { "progress_cb": progress_cb
                  , "request_future": request_future
                  , "request_handler": request_handler
                  }
                , extra_options or {}
                , dont_prefix = [dictobj]
                )

            meta = Meta(everything, self.meta.path).at("<input>")
            command = self.command_spec.normalise(meta, {"path": path, "body": body})

            return await command.execute()
        finally:
            request_future.cancel()