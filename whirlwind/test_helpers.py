"""
Whirlwind provides some functionality to make it easier to write tests for your
server.

.. autofunction:: free_port

.. autofunction:: port_connected

.. autofunction:: with_timeout

.. autofunction:: async_as_background

.. autofunction:: modified_env

.. autoclass:: AsyncTestCase
    :members:

.. autoclass:: ServerRunner
    :members:

.. autoclass:: ModuleLevelServer
    :members:

.. autoclass:: WSStream
    :members:
"""
from asynctest import TestCase as AsyncTestCase
from tornado.websocket import websocket_connect
from tornado.httpclient import AsyncHTTPClient
from input_algorithms import spec_base as sb
from contextlib import contextmanager
from functools import partial
import logging
import asyncio
import socket
import uuid
import time
import json
import sys
import os

log = logging.getLogger("whirlwind.test_helpers")

def free_port():
    """
    Return an unused port number
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', 0))
        return s.getsockname()[1]

def port_connected(port):
    """
    Return whether something is listening on this port
    """
    s = socket.socket()
    s.settimeout(5)
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except Exception:
        return False

def with_timeout(func):
    """
    A decorator that returns an async function that runs the original function
    with a timeout

    It assumes you are decorating a method on a class with a ``wait_for`` method
    like ``whirlwind.test_helpers.AsyncTestCase``

    .. code-block:: python

        from whirlwind import test_helpers as wthp

        import asyncio

        class TestSomething(wthp.AsyncTestCase):
            @wthp.with_timeout
            async def test_waiting(self):
                # This will assert False cause the function takes too long
                await asyncio.sleep(20)
    """
    async def test(s):
        await s.wait_for(func(s))
    test.__name__ = func.__name__
    return test

def async_as_background(coro):
    """
    Start a coroutine as an asyncio task with a done callback that prints out
    any exception. This is useful to start a coroutine running without waiting
    for it at the same time, and making sure you don't get warnings later on if
    it has an uncaught exception.

    .. code-block:: python

        from whirlwind import test_helpers as wthp

        import asyncio

        async def doit():
            ...
            await asyncio.sleep(2)
            ...

        task = wthp.async_as_background(doit())
        ...
        await task
    """
    def reporter(res):
        if not res.cancelled():
            exc = res.exception()
            if exc:
                log.exception(exc, exc_info=(type(exc), exc, exc.__traceback__))
    t = asyncio.get_event_loop().create_task(coro)
    t.add_done_callback(reporter)
    return t

@contextmanager
def modified_env(**env):
    """
    A context manager that let's you modify environment variables until the block
    has ended where the environment is returned to how it was

    .. code-block:: python

        from whirlwind import test_helpers as wthp

        import os

        assert "ONE" not in os.environ
        assert os.environ["TWO"] == "two"

        with wthp.modified_env(ONE="1", TWO="2"):
            assert os.environ["ONE"] == "1"
            assert os.environ["TWO"] == "1"

        assert "ONE" not in os.environ
        assert os.environ["TWO"] == "two"
    """
    previous = {key: os.environ.get(key, sb.NotSpecified) for key in env}
    try:
        for key, val in env.items():
            os.environ[key] = val
        yield
    finally:
        for key, val in previous.items():
            if val is sb.NotSpecified:
                if key in os.environ:
                    del os.environ[key]
            else:
                os.environ[key] = val

class AsyncTestCase(AsyncTestCase):
    """
    This is a class that inherits from asynctest.TestCase. This is essentially
    the same as unittest.TestCase but async.

    It also comes with a ``wait_for`` helper for waiting on coroutines with a
    timeout

    .. code-block:: python

        from whirlwind import test_helpers as wthp

        import asyncio

        class TestSomething(wthp.AsyncTestCase):
            async def test_something_works(self):
                fut = asyncio.Future()
                # This will cause an assertion error cause future never resolves!
                await self.wait_for(fut)
    """
    async def wait_for(self, fut, timeout=1):
        """Await for this future and assert False if it takes longer than the timeout"""
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as error:
            assert False, "Failed to wait for future before timeout: {0}".format(error)

class WSStream:
    """
    A helper for creating a websocket stream and sending/receiving messages on it.

    It works with the shape of a websocket message according to whirlwind and
    let's you work with the message_id per message without having to care about
    it yourself.

    It takes in two things:

    server
        An object with ``ws_connect()``, ``ws_read(conn)`` and
        ``ws_write(conn, msg)``

        ``ws_connect()`` must create a connection to the server and return an
        object that can be used with ``ws_read`` and ``ws_write``

        ``ws_read(conn)`` reads a message from the server and returns it. If the
        connection is closed it should return ``None``

        ``ws_write(conn, msg)`` will write ``msg`` to the connection.

    test
        An object with ``assertIs`` and ``assertEqual`` on it for asserting
        identity and equality respectively.

    It is likely you would access this object via the ``ws_stream`` method on
    a ``ServerRunner`` object.

    You use the WSStream object as an async contextmanager and then use ``start``
    and ``check_reply`` on the stream

    .. code-block:: python

        from whirlwind import test_helpers as wthp

        from unittest import mock

        # let's assume server is a ServerRunner instance and test is a
        # unittest.TestCase instance

        async with wthp.WSStream(server, test) as stream:
            # Send ``{"path": "/path/in/message", "body": {"arg": 1}, "message_id": <message_id>}``
            # And record ``<message_id>`` so it can be used in check_reply
            await stream.start("/path/in/message", {"arg": 1})

            # Check that we get back ``{"message_id": <message_id>, "reply": {"response": True}}``
            # reply will equal {"response": True}
            reply = await stream.check_reply({"response": True})

            # Hack to get the reply without caring about how it looks
            reply = await stream.check_reply(mock.ANY)

            # And we can start a new message. Note that WSStream assumes you've
            # finished with this message_id when you do this
            await stream.start("/anotherpath/message", {"arg": 2})
            await stream.check_reply({"sucess": False})

        # When the context manager is exited, the stream is closed and we assert
        # that there are no new messages left
    """
    def __init__(self, server, test):
        self.test = test
        self.server = server

    async def __aenter__(self):
        self.connection = await self.server.ws_connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if hasattr(self, "connection"):
            self.connection.close()
            try:
                self.test.assertIs(await self.server.ws_read(self.connection), None)
            except AssertionError:
                if exc_type is not None:
                    exc.__traceback__ = tb
                    raise exc
                raise

    async def start(self, path, body):
        self.message_id = str(uuid.uuid1())
        await self.server.ws_write(self.connection, {"path": path, "body": body, "message_id": self.message_id})

    async def check_reply(self, reply):
        d, nd = await asyncio.wait([self.server.ws_read(self.connection)], timeout=5)
        if nd:
            assert False, "Timedout waiting for future"

        got = await list(d)[0]
        wanted = {"message_id": self.message_id, "reply": reply}
        if got != wanted:
            print("got --->")
            print(got)
            print("wanted --->")
            print(wanted)

        self.test.assertEqual(got, wanted)
        return got["reply"]

class ServerRunner:
    """
    A helper for creating a server and then connecting to it.

    We take in:

    final_future
        A future that the server should be looking at. We cancel this future
        when we want to shutdown the server.

    port
        The port to serve on

    server
        An object with a ``serve(host, port, *args, **kwargs)`` method. This
        serve method is called when we start the server. It is assumed that the
        server will stop itself when the ``final_future`` is cancelled.

    wrapper
        A contextmanager instance that is used around ``server.serve``.

        Essentially:

        .. code-block:: python

            with wrapper:
                await server.serve(...)

    ``*args`` and ``**kwargs``
        These are passed into the ``setup`` method. By default we store these as
        ``self.server_args`` and ``self.server_kwargs`` and they are passed into
        ``server.serve``

    This class can be used as a async contextmanager, like:

    .. code-block:: python

        from whirlwind import test_helpers as wthp

        class TestPath(wthp.AsyncTestCase):
            async def test_something(self):
                async with WSServer(...) as server:
                    await server.assertGET(self, "/v1/path", json_output={"success": True"})

    Using it as an async contextmanager is the same as saying:

    .. code-block:: python

        server = WSServer(...)
        try:
            await server.start()
        finally:
            await server.close(*sys.exc_info())

    If you are making multiple assertions to your server, it is reccomended you
    use this class via ``whirlwind.test_helpers.ModuleLevelServer``
    """
    def __init__(self, final_future, port, server, wrapper, *args, **kwargs):
        if wrapper is None:
            @contextmanager
            def wrapper():
                yield
            wrapper = wrapper()

        self.port = port
        self.server = server
        self.wrapper = wrapper
        self.final_future = final_future
        self.setup(*args, **kwargs)

    def setup(self, *args, **kwargs):
        """
        Used to take in extra ``*args`` and ``**kwargs`` passed into ``__init__``.

        If you override this method it is reccomended you call ``super().setup(*args, **kwargs)``
        so that ``self.server_args`` and ``self.server_kwargs`` are set.
        """
        self.server_args = args
        self.server_kwargs = kwargs

    async def closer(self):
        d, nd = await asyncio.wait([self.close(None, None, None)], timeout=5)

        if d:
            await list(d)[0]
        else:
            assert False, "Failed to shutdown the server"

    async def before_start(self):
        """Hook called before the server has started"""

    async def after_close(self, exc_type, exc, tb):
        """Hook called when this server is closed"""

    def ws_stream(self, test):
        """Helper to return a WSStream object for this server"""
        return WSStream(self, test)

    async def after_ws_open(self, connection):
        """
        Hook called when a websocket connection is made

        By default this method will just assert that we get back a ``__server_time__``
        message after the connection is made.
        """
        class ATime:
            def __eq__(self, other):
                return type(other) is float

        first = await self.ws_read(connection)
        assert first == {"reply": ATime(), "message_id": "__server_time__"}, first

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, typ, exc, tb):
        await self.close(typ, exc, tb)

    async def start(self):
        """
        Run our ``before_start`` hook, start the server and wait for it to be
        listening on our port.
        """
        await self.before_start()

        async def doit():
            with self.wrapper:
                await self.server.serve("127.0.0.1", self.port, *self.server_args, **self.server_kwargs)
        assert not port_connected(self.port)
        self.t = async_as_background(doit())

        start = time.time()
        while time.time() - start < 5:
            if port_connected(self.port):
                break
            await asyncio.sleep(0.001)
        assert port_connected(self.port)
        return self

    async def close(self, typ, exc, tb):
        """
        Cancel the final future, wait for our server to close, call our ``after_close``
        hook and assert that nothing is listening to our port anymore.
        """
        if typ is not None:
            log.error("Something went wrong", exc_info=(typ, exc, tb))

        self.final_future.cancel()
        if not hasattr(self, "t"):
            return

        if self.t is not None and not self.t.done():
            try:
                await asyncio.wait_for(self.t, timeout=5)
            except asyncio.CancelledError:
                pass

        await asyncio.wait_for(self.after_close(typ, exc, tb), timeout=5)

        assert not port_connected(self.port)

    @property
    def ws_path(self):
        """Hook to return the path to the websocket handler on the server"""
        return "/v1/ws"

    @property
    def ws_url(self):
        """
        Hook to return the websocket address to our websocket handler

        .. code-block:: python

            f"ws://127.0.0.1:{self.port}{self.ws_path}"
        """
        return f"ws://127.0.0.1:{self.port}{self.ws_path}"

    async def ws_connect(self):
        """
        Create a connection to our ``self.ws_url``, call the ``after_ws_open``
        hook with the connection and return the connection.
        """
        connection = await websocket_connect(self.ws_url)

        await self.after_ws_open(connection)

        return connection

    async def ws_write(self, connection, message):
        """Write a message to the connection. We json.dumps the message before sending it"""
        return await connection.write_message(json.dumps(message))

    async def ws_read(self, connection):
        """
        Read from the connection and return the result. If the result is not None
        we json.loads it first.
        """
        res = await connection.read_message()
        if res is None:
            return res
        return json.loads(res)

    async def assertGET(self, test, path, status=200, json_output=None, text_output=None):
        """Run ``self.assertHTTP`` with the GET method."""
        return await self.assertHTTP(test, path, "GET", {}
            , status = status
            , json_output = json_output
            , text_output = text_output
            )

    async def assertPOST(self, test, path, body, status=200, json_output=None, text_output=None):
        """Run ``self.assertHTTP`` with the POST method."""
        return await self.assertHTTP(test, path, "POST", {"body": json.dumps(body).encode()}
            , status = status
            , json_output = json_output
            , text_output = text_output
            )

    async def assertPUT(self, test, path, body, status=200, json_output=None, text_output=None):
        """Run ``self.assertHTTP`` with the PUT method."""
        return await self.assertHTTP(test, path, "PUT", {"body": json.dumps(body).encode()}
            , status = status
            , json_output = json_output
            , text_output = text_output
            )

    async def assertPATCH(self, test, path, body, status=200, json_output=None, text_output=None):
        """Run ``self.assertHTTP`` with the PATCH method."""
        return await self.assertHTTP(test, path, "PATCH", {"body": json.dumps(body).encode()}
            , status = status
            , json_output = json_output
            , text_output = text_output
            )

    async def assertDELETE(self, test, path, status=200, json_output=None, text_output=None):
        """Run ``self.assertHTTP`` with the DELETE method."""
        return await self.assertHTT(test, path, "DELETE", {}
            , status = status
            , json_output = json_output
            , text_output = text_output
            )

    async def assertHTTP(self, test, path, method, kwargs, status=200, json_output=None, text_output=None):
        """
        Make a HTTP request to the server and make assertions about the result.
        The body of the response is returned.

        test
            An object with ``assertEqual`` on it for asserting equality

        path
            The HTTP path

        method
            The HTTP method

        kwargs
            We make the HTTP request using the ``fetch``method on
            ``tornado.httpclient.AsyncHTTPClient``. kwargs is extra arguments
            to give to fetch. Like ``body`` or ``headers``.

        status
            The HTTP status we expect back

        json_output
            If not None then we json.loads the body of the response and assert
            equality with ``json_output``

        text_output
            If not None then assert the response body equals ``text_output``
        """
        client = AsyncHTTPClient()

        if "raise_error" not in kwargs:
            kwargs['raise_error'] = False

        response = await client.fetch(f"http://127.0.0.1:{self.port}{path}"
            , method = method
            , **kwargs
            )

        output = response.body
        test.assertEqual(response.code, status, output)

        if json_output is None and text_output is None:
            return output
        else:
            if json_output is not None:
                self.maxDiff = None
                try:
                    test.assertEqual(json.loads(output.decode()), json_output)
                except AssertionError:
                    print(json.dumps(json.loads(output.decode()), sort_keys=True, indent="    "))
                    raise
            else:
                test.assertEqual(output, text_output)

class ModuleLevelServer:
    """
    A helper for creating a WSServer instance and managing it so it starts at
    before the tests in your test module and closes after all the tests are done.

    This is to allow you to split your testing across many test functions but
    not have to wait for the server to start and close for every test.

    It creates it's own asyncio.Loop object and so if you are using
    ``asynctest.TestCase`` you have to tell it to not create it's own loop.

    This object takes in ``*args`` and ``**kwargs`` that are passed to the
    ``server_runner`` hook that you must implement.

    Usage looks like this:

    .. code-block:: python

        from whirlwind import test_helpers as wthp

        from my_application import Server

        class M(wthp.ModuleLevelServer):
            async def started_test(self):
                # Hook called at the start of each test

            async def exception_from_test(self, exc_type, exc, tb):
                # Hook called for each test that fails with an exception

            async def finished_test(self):
                # Hook called after every test regardless of failure

            async def server_runner(self):
                self.final_future = asyncio.Future()

                server = Server(self.final_future)
                runner = ServerRunner(self.final_future, wthp.free_port(), server, None)

                await runner.start()
                return runner, runner.closer

            async def run_test(self, func):
                # Hook to override if you want to pass in things to the test itself
                return await func(self.runner)

        test_server = M()

        # Let the server be started and cleaned up at the module level
        setUp = test_server.setUp
        tearDown = test_server.tearDown

        class TestMyServer(wthp.AsyncTestCase):
            # Use the loop created by the ModuleLevelServer
            use_default_loop = True

            @test_server.test
            async def test_it_works(self, runner):
                await runner.assertGET(self, "/v1/somewhere", json_output={"one": "two"})

            @test_server.test
            async def test_it_works_twice(self, runner):
                await runner.assertGET(self, "/v1/somewhere-else", json_output={"three": "four"})
    """
    def __init__(self, *args, **kwargs):
        self.loop = asyncio.new_event_loop()

        self.args = args
        self.kwargs = kwargs

    async def server_runner(self, *args, **kwargs):
        """
        Hook to create a ServerRunner

        Must return (runner, closer)

        Where closer is a coroutine that is called to shutdown the runner
        """
        raise NotImplementedError()

    async def run_test(self, func):
        """Hook to override if you want to pass in things to the test itself"""
        return await func(self.runner)

    def setUp(self):
        """
        Set the loop to our loop and use ``serve_runner`` to get a runner and
        closer
        """
        asyncio.set_event_loop(self.loop)
        self.runner, self.closer = self.loop.run_until_complete(self.server_runner(*self.args, **self.kwargs))

    def tearDown(self):
        """
        Call our closer function returned from ``server_runner`` and set close
        our loop
        """
        if self.closer is not None:
            self.loop.run_until_complete(self.closer())
        self.loop.close()
        asyncio.set_event_loop(None)

    async def started_test(self):
        """Hook called at the start of each test"""

    async def exception_from_test(self, exc_type, exc, tb):
        """Hook called for each test that fails with an exception"""

    async def finished_test(self):
        """Hook called after every test regardless of failure"""

    def test(self, func):
        """
        A decorator for each test that ensures our ``started_test``,
        ``exception_from_test`` and ``finished_test`` hooks are called.

        We also timeout the function after 10 seconds.

        And we use our ``run_test`` hook to provide extra arguments to the
        function.
        """
        async def test(s):
            await self.started_test()
            s.maxDiff = None
            try:
                await s.wait_for(self.run_test(partial(func, s)), timeout=10)
            except:
                await self.exception_from_test(*sys.exc_info())
                raise
            finally:
                await self.finished_test()

        test.__name__ = func.__name__
        return test
