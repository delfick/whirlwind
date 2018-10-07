from asynctest import TestCase as AsyncTestCase
from tornado.websocket import websocket_connect
from tornado.httpclient import AsyncHTTPClient
from input_algorithms import spec_base as sb
from contextlib import contextmanager
from functools import partial
import http.client
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
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', 0))
        return s.getsockname()[1]

def port_connected(port):
    s = socket.socket()
    s.settimeout(5)
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except Exception:
        return False

def async_as_background(coro):
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
    async def wait_for(self, fut, timeout=1):
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as error:
            assert False, "Failed to wait for future before timeout: {0}".format(error)

class WSStream:
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

        self.server_args = args
        self.server_kwargs = kwargs

    def test_start(self):
        """Hook called at the start of each test from ModuleLevelServer"""

    def test_exception(self, exc_type, exc, tb):
        """Hook called for each test that fails with an exception from ModuleLevelServer"""

    def test_final(self):
        """Hook called after every test regardless of failure from ModuleLevelServer"""

    async def after_close(self):
        """Hook called when this server is closed"""

    def ws_stream(self, test):
        return WSStream(self, test)

    async def after_open(self, connection):
        """Hook called when this server is started"""
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

        await asyncio.wait_for(self.after_close(), timeout=5)

        assert not port_connected(self.port)

    @property
    def ws_path(self):
        return "/v1/ws"

    @property
    def ws_url(self):
        return f"ws://127.0.0.1:{self.port}{self.ws_path}"

    async def ws_connect(self):
        connection = await websocket_connect(self.ws_url)

        await self.after_open(connection)

        return connection

    async def ws_write(self, connection, message):
        return await connection.write_message(json.dumps(message))

    async def ws_read(self, connection):
        res = await connection.read_message()
        if res is None:
            return res
        return json.loads(res)

    async def assertPUT(self, test, path, body, status=200, json_output=None, text_output=None, timeout=None):
        client = AsyncHTTPClient()

        response = await client.fetch(f"http://127.0.0.1:{self.port}{path}"
            , method="PUT"
            , body=json.dumps(body).encode()
            , raise_error=False
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

def with_timeout(func):
    async def test(s):
        await s.wait_for(func(s))
    test.__name__ = func.__name__
    return test

class ModuleLevelServer:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.server = None
        self.closer = None
        self.record_lines_read = 0

    async def server_runner(self):
        """
        Hook to create a ServerRunner

        Must return (server, closer)

        Where closer is a coroutine that is called to shutdown the server
        """
        raise NotImplementedError()

    async def run_test(self, func):
        """Hook to override if you want to pass in things to the test itself"""
        return await func()

    def setUp(self):
        asyncio.set_event_loop(self.loop)
        self.server, self.closer = self.loop.run_until_complete(self.server_runner())

    def tearDown(self):
        if self.closer is not None:
            self.loop.run_until_complete(self.closer())
        self.loop.close()
        asyncio.set_event_loop(None)

    def test(self, func):
        async def test(s):
            self.server.test_start()
            s.maxDiff = None
            try:
                await s.wait_for(self.run_test(partial(func, s)), timeout=10)
            except:
                self.server.test_exception(*sys.exc_info())
                raise
            finally:
                # Make sure the test is aware of all the records that test produces
                self.server.test_final()

        test.__name__ = func.__name__
        return test
