# coding: spec

from whirlwind.server import wait_for_futures
from whirlwind import test_helpers as thp

import asyncio

describe thp.AsyncTestCase, "wait_for_futures":
    @thp.with_timeout
    async it "waits on not done future and ignores failures":
        pending_fut1 = asyncio.Future()
        asyncio.get_event_loop().call_later(0.1, pending_fut1.set_result, True)

        pending_fut2 = asyncio.Future()
        asyncio.get_event_loop().call_later(0.2, pending_fut2.set_exception, TypeError("asdf"))

        pending_fut3 = asyncio.Future()
        asyncio.get_event_loop().call_later(0.2, pending_fut3.cancel)

        done_fut1 = asyncio.Future()
        done_fut1.set_result(False)

        done_fut2 = asyncio.Future()
        done_fut2.cancel()

        done_fut3 = asyncio.Future()
        done_fut3.set_exception(ValueError("NAH"))

        futures = {
              1: pending_fut1, 2: pending_fut2, 3: pending_fut3
            , 4: done_fut1, 5: done_fut2, 6: done_fut3
            }

        await wait_for_futures(futures)
        assert True, "Successfully waited!"

        for fut in futures.values():
            assert fut.done()
