Interactive Commands
====================

When you use the ``commander`` to create commands, you can make a command that
can take in multiple requests to the same command. For example:

.. code-block:: python

    @store.command("interactive")
    class Interactive(store.Command):
        progress_cb = store.injected("progress_cb")

        max_commands = dictobj.Field(sb.integer_spec, default=10)

        async def execute(self, messages):
            count = 0
            interactives = []

            # Good idea to give a progress cb saying we have started
            # So that clients know they can add more commands
            self.progres_cb("started")

            async for message in messages:
                count += 1
                t = message.process()

                if t.interactive:
                    interactives.append(t)
                else:
                    res = await message.process()
                    self.progress_cb({
                        "processed": message.command.__name__,
                        "result": res
                    })

                if count >= self.max_commands:
                    break

            if interactives:
                for i in interactives:
                    i.cancel()
                await asyncio.wait([interactives])

    @store.command("command1", parent=Interactive)
    class Command1(store.Command):
        option1 = dictobj.Field(sb.string_spec, wrapper=sb.required)

        async def execute(self):
            return self.option1

    @store.command("command2", parent=Interactive)
    class Command2(store.Command):
        flag = dictobj.Field(sb.boolean, default=False)

        async def execute(self):
            return self.flag

    @store.command("command3", parent=Interactive)
    class Command3(store.Command):
        flag = dictobj.Field(sb.boolean, default=False)

        async def execute(self, messages):
            self.progress_cb("started")

            async for message in messages:
                # Important to mark the message as received
                message.no_process()

                self.progress_cb(f"got {message.command.__name__}")

    @store.command("command4", parent=Command3)
    class Command4(store.Command):
        async def execute(self):
            pass

Interactive commands may themselves have interactive commands as children and
when you call ``message.process()`` you will get a task back that represents
the completion of that command.

You can determine if the message is also interactive by accessing the
``interactive`` property on the ``message``. And you can access the command
itself by looking at ``message.command``. If you don't want to run the execute
method on the command, then run ``message.no_process()`` so that finishing the
parent command doesn't hang waiting for the message to be resolved.

.. note:: interactive commands and their children are not exposed to the http
    endpoints that can be made from the commander.

To use the children commands you supply ``message_id`` as a tuple of all the
``message_id`` values that led to that command.

So say we started the ``Interactive`` command above with::

    {
      "path": "/v1",
      "body": {
        "command": "interactive",
        "message_id": "MSG1", 
        "args": {"max_commands": 5}
      }
    }

We can then add a command by saying::

    {
      "path": "/v1",
      "body": {
        "command": "command1",
        "message_id": ["MSG1", "MSG2"]
        "args": {"option1": 5}
      }
    }

And to go deeper we could do::

    {
      "path": "/v1",
      "body": {
        "command": "command3",
        "message_id": ["MSG1", "MSG3"]
        "args": {"option1": 5}
      }
    }

    {
      "path": "/v1",
      "body": {
        "command": "command4",
        "message_id": ["MSG1", "MSG3", "MSG4"]
      }
    }
