from whirlwind.request_handlers.base import Simple, SimpleWebSocketBase

import logging
import inspect

log = logging.getLogger("whirlwind.request_handlers.command")

class ProgressCB:
    def __init__(self, stack_level):
        frm = inspect.stack()[stack_level]
        mod = inspect.getmodule(frm[0])
        self.logger_name = mod.__name__

    def __call__(self, body, message, do_log=True, **kwargs):
        info = self.make_info(body, message, **kwargs)
        if do_log:
            self.do_log(body, message, info, **kwargs)
        return info

    def make_info(self, body, message, **kwargs):
        info = {}

        if isinstance(message, Exception):
            info["error_code"] = message.__class__.__name__
            if hasattr(message, "as_dict"):
                info["error"] = message.as_dict()
            else:
                info["error"] = str(message)
        elif message is None:
            info["done"] = True
        else:
            info["info"] = message

        info.update(kwargs)
        return info

    def do_log(self, body, message, info, **kwargs):
        pass

class ProcessReplyMixin:
    def process_reply(self, msg, exc_info=None):
        try:
            self.commander.process_reply(msg, exc_info)
        except KeyboardInterrupt:
            raise
        except Exception as error:
            log.exception(error)

class CommandHandler(Simple, ProcessReplyMixin):
    def initialize(self, commander, progress_cb):
        self.commander = commander
        self.progress_cb = progress_cb

    async def do_put(self):
        j = self.body_as_json()

        def progress_cb(message, stack_extra=0, **kwargs):
            cb = self.progress_cb(2 + stack_extra)
            info = cb(j, message, **kwargs)
            self.process_reply(info)

        return await self.commander.execute(self.request.path, j, progress_cb, self)

class WSHandler(SimpleWebSocketBase, ProcessReplyMixin):
    def initialize(self, server_time, wsconnections, commander, progress_cb):
        self.commander = commander
        self.progress_cb = progress_cb
        super().initialize(server_time, wsconnections)

    async def process_message(self, path, body, message_id, progress_cb):
        def pcb(message, stack_extra=0, **kwargs):
            cb = self.progress_cb(2 + stack_extra)
            info = cb(body, message, **kwargs)
            progress_cb(info)

        return await self.commander.execute(path, body, pcb, self)
