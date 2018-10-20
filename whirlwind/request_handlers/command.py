from whirlwind.request_handlers.base import Simple, SimpleWebSocketBase, Finished
from whirlwind.store import NoSuchPath

import logging
import inspect

log = logging.getLogger("whirlwind.request_handlers.command")

class ProgressMessageMaker:
    def __init__(self, stack_level=0):
        frm = inspect.stack()[1 + stack_level]
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
    progress_maker = ProgressMessageMaker

    def initialize(self, commander):
        self.commander = commander

    async def do_put(self):
        j = self.body_as_json()

        def progress_cb(message, stack_extra=0, **kwargs):
            maker = self.progress_maker(1 + stack_extra)
            info = maker(j, message, **kwargs)
            self.process_reply(info)

        path = self.request.path
        while path and path.endswith("/"):
            path = path[:-1]

        try:
            return await self.commander.executor(progress_cb, self).execute(path, j)
        except NoSuchPath as error:
            raise Finished(status=404, wanted=error.wanted, available=error.available, error="Specified path is invalid")

class WSHandler(SimpleWebSocketBase, ProcessReplyMixin):
    progress_maker = ProgressMessageMaker

    def initialize(self, server_time, wsconnections, commander):
        self.commander = commander
        super().initialize(server_time, wsconnections)

    async def process_message(self, path, body, message_id, message_key, progress_cb):
        def pcb(message, stack_extra=0, **kwargs):
            maker = self.progress_maker(1 + stack_extra)
            info = maker(body, message, **kwargs)
            progress_cb(info)

        try:
            executor = self.commander.executor(pcb, self, message_key=message_key, message_id=message_id)
            return await executor.execute(path, body)
        except NoSuchPath as error:
            raise Finished(status=404, wanted=error.wanted, available=error.available, error="Specified path is invalid")
