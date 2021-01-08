from whirlwind import Commander, Server

from unittest import mock
import asyncio
import aiohttp
import pytest
import socket
import errno
import json
import uuid
import time
import sys


class memoized_property:
    class Empty:
        pass

    def __init__(self, func):
        self.func = func
        self.name = func.__name__
        self.cache_name = "_{0}".format(self.name)

    def __get__(self, instance=None, owner=None):
        if instance is None:
            return self

        if getattr(instance, self.cache_name, self.Empty) is self.Empty:
            setattr(instance, self.cache_name, self.func(instance))
        return getattr(instance, self.cache_name)


def _port_connected(port):
    """
    Return whether something is listening on this port
    """
    with socket.socket() as sock:
        res = int(sock.connect_ex(("127.0.0.1", port)))

    if res == 0:
        return True

    error = errno.errorcode[res]
    assert res == errno.ECONNREFUSED, (error, port)
    return False


@pytest.helpers.register
def AsyncMock(*args, **kwargs):
    if sys.version_info >= (3, 8):
        return mock.AsyncMock(*args, **kwargs)
    else:
        return __import__("mock").AsyncMock(*args, **kwargs)


@pytest.helpers.register
def create_future(*args, **kwargs):
    return asyncio.get_event_loop().create_future(*args, **kwargs)


@pytest.helpers.register
def create_task(*args, **kwargs):
    return asyncio.get_event_loop().create_task(*args, **kwargs)


@pytest.helpers.register
def port_connected(port):
    return _port_connected(port)


@pytest.helpers.register
async def wait_for_port(port, timeout=3, gap=0.01):
    """
    Wait for a port to have something behind it
    """
    start = time.time()
    while time.time() - start < timeout:
        if _port_connected(port):
            break
        await asyncio.sleep(gap)
    assert _port_connected(port)


@pytest.helpers.register
async def wait_for_no_port(port, timeout=3, gap=0.01):
    """
    Wait for a port to not have something behind it
    """
    start = time.time()
    while time.time() - start < timeout:
        if not _port_connected(port):
            break
        await asyncio.sleep(gap)
    assert not _port_connected(port)


@pytest.helpers.register
def free_port():
    """
    Return an unused port number
    """
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.helpers.register
def assertComparison(got, wanted, *, is_json):
    if got != wanted:
        print("!" * 80)
        print("Reply was unexpected")
        print("Got:")
        if is_json:
            got = json.dumps(got, sort_keys=True, indent="  ", default=lambda o: repr(o))
        for line in got.split("\n"):
            print(f"> {line}")

        print("Wanted:")
        if is_json:
            wanted = json.dumps(wanted, sort_keys=True, indent="  ", default=lambda o: repr(o))
        for line in wanted.split("\n"):
            print(f"> {line}")

    assert got == wanted
    return got


@pytest.helpers.register
class Empty:
    pass


class WSTester:
    def __init__(self, port, path="/v1/ws", gives_server_time=True):
        self.path = path
        self.port = port
        self.message_id = None
        self.gives_server_time = gives_server_time

    async def __aenter__(self):
        try:
            self.session = aiohttp.ClientSession()
            self.ws = await self.session.ws_connect(f"ws://127.0.0.1:{self.port}{self.path}")

            if self.gives_server_time:

                class IsNum:
                    def __eq__(self, value):
                        self.got = value
                        return type(value) is float

                    def __repr__(self):
                        if hasattr(self, "got"):
                            return repr(self.got)
                        else:
                            return "<NOVALUE_COMPARED>"

                await self.check_reply(IsNum(), message_id="__server_time__")

        except:
            exc_info = sys.exc_info()
            await self.__aexit__(*exc_info)
            raise

        return self

    async def __aexit__(self, exc_typ, exc, tb):
        try:
            if hasattr(self, "ws"):
                await self.ws.close()
                await self.ws.receive() is None
        finally:
            if hasattr(self, "session"):
                await self.session.close()

    async def start(self, path, body, message_id=None):
        if message_id is None and message_id != "__server_time__":
            self.message_id = message_id = str(uuid.uuid1())

        msg = {"path": path, "message_id": message_id}
        if body is not pytest.helpers.Empty:
            msg["body"] = body

        await self.ws.send_json(msg)
        return message_id

    async def check_reply(self, reply, message_id=None):
        got = await self.ws.receive_json()
        wanted = {
            "reply": reply,
            "message_id": self.message_id if message_id is None else message_id,
        }
        return pytest.helpers.assertComparison(got, wanted, is_json=True)["reply"]


class BareServer(Server):
    async def setup(self, store, tornado_routes, wsconnections, server_time):
        self.commander = Commander(store)
        self.server_time = server_time
        self.wsconnections = wsconnections
        self._tornado_routes = tornado_routes

    def tornado_routes(self):
        return self._tornado_routes(self)


class MockServer:
    def __init__(self, *, start_server=False, Server, server_args, server_kwargs):
        self.port = pytest.helpers.free_port()
        self.Server = Server
        self.server_args = server_args
        self.start_server = start_server
        self.server_kwargs = server_kwargs

        self.cleaners = []

    def per_test(self):
        pass

    def ws_stream(self, path="/v1/ws", gives_server_time=True):
        return WSTester(self.port, path=path, gives_server_time=gives_server_time)

    async def assertHTTP(
        self,
        method,
        path,
        kwargs,
        status=200,
        json_output=None,
        text_output=None,
        expected_headers=None,
    ):
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
            The extra arguments to give the call

        status
            The HTTP status we expect back

        json_output
            If not None we compare the json output from the response

        text_output
            If not None we compare the text output from the response

        expected_headers
            The headers we expect in the response
        """
        async with aiohttp.ClientSession() as session:
            async with getattr(session, method.lower())(
                f"http://127.0.0.1:{self.port}{path}", **kwargs
            ) as res:
                if json_output is not None:
                    content = await res.json()
                    pytest.helpers.assertComparison(content, json_output, is_json=True)
                elif text_output is not None:
                    content = await res.text()
                    pytest.helpers.assertComparison(content, text_output, is_json=False)
                else:
                    content = await res.read()

                assert res.status == status

                if expected_headers is not None:
                    for k, v in expected_headers.items():
                        assert res.headers[k] == v

                return content

    @memoized_property
    def final_future(self):
        return pytest.helpers.create_future()

    @memoized_property
    def server(self):
        return self.Server(self.final_future)

    async def __aenter__(self):
        if not self.start_server:
            await self.server.setup(*self.server_args, *self.server_kwargs)
            return self

        assert not pytest.helpers.port_connected(self.port)

        self._task = pytest.helpers.create_task(
            self.server.serve("127.0.0.1", self.port, *self.server_args, **self.server_kwargs)
        )

        await pytest.helpers.wait_for_port(self.port)

        return self

    async def __aexit__(self, exc_typ, exc, tb):
        self.final_future.cancel()
        if hasattr(self, "_task"):
            await asyncio.wait([self._task])

        ct = pytest.helpers.create_task
        cleaner_tasks = [ct(cleaner()) for cleaner in self.cleaners]
        no_port_task = ct(pytest.helpers.wait_for_no_port(self.port))

        if self.wsconnections:
            await asyncio.wait(list(self.wsconnections.values()))
        if cleaner_tasks:
            await asyncio.wait(cleaner_tasks)
        await asyncio.wait([no_port_task])

        for task in cleaner_tasks + [no_port_task]:
            if task.done():
                await task


class ServerWrapper(MockServer):
    def __init__(self, store, tornado_routes, start_server=True, **kwargs):
        self.wsconnections = {}
        super().__init__(
            start_server=start_server,
            Server=BareServer,
            server_args=(store, tornado_routes, self.wsconnections, time.time()),
            server_kwargs={},
        )


@pytest.fixture(scope="session")
def mock_server():
    return MockServer


@pytest.fixture(scope="session")
def server_wrapper():
    return ServerWrapper
