import asyncio
import contextlib
import functools
import inspect
import itertools
from asyncio import Event, Lock

import asynctest
from aiomysql.sa import create_engine
from hypothesis.internal.reflection import (
    define_function_signature,
    impersonate
)


# Copied over from PR #113 of pytest-asyncio. It will probably be available in
# the library in a few months.
class EventLoopClockAdvancer:
    """
    A helper object that when called will advance the event loop's time. If the
    call is awaited, the caller task will wait an iteration for the update to
    wake up any awaiting handlers.
    """

    __slots__ = ("offset", "loop", "sleep_duration", "_base_time")

    def __init__(self, loop, sleep_duration=1e-6):
        self.offset = 0.0
        self._base_time = loop.time
        self.loop = loop
        self.sleep_duration = sleep_duration

        # incorporate offset timing into the event loop
        self.loop.time = self.time

    def time(self):
        """
        Return the time according to the event loop's clock. The time is
        adjusted by an offset.
        """
        return self._base_time() + self.offset

    async def __call__(self, seconds):
        """
        Advance time by a given offset in seconds. Returns an awaitable
        that will complete after all tasks scheduled for after advancement
        of time are proceeding.
        """
        # sleep so that the loop does everything currently waiting
        await asyncio.sleep(self.sleep_duration)

        if seconds > 0:
            # advance the clock by the given offset
            self.offset += seconds

            # Once the clock is adjusted, new tasks may have just been
            # scheduled for running in the next pass through the event loop
            await asyncio.sleep(self.sleep_duration)


def fast_forward(timeout):
    def deco(f):
        @functools.wraps(f)
        async def awaiter(*args, **kwargs):
            loop = asyncio.get_event_loop()
            advance_time = EventLoopClockAdvancer(loop)
            time = 0
            fut = asyncio.create_task(f(*args, **kwargs))

            while not fut.done() and time < timeout:
                await asynctest.exhaust_callbacks(loop)
                await advance_time(0.1)
                time += 0.1

            return await fut

        return awaiter
    return deco


class MockConnectionContext:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        await self._db._lock.acquire()
        return self._db._connection

    async def __aexit__(self, exc_type, exc, tb):
        self._db._lock.release()


class MockDatabase:
    """
    This class mocks the FAFDatabase class, rolling back all transactions
    performed during tests. To do that, it proxies the real db engine, giving
    access to a single connection the results of which are never comitted.
    Since the server uses that single connection, it sees all changes made, but
    at the same time we can rollback all these changes once the test is over.

    Note that right now the server relies on autocommit behaviour of aiomysql.
    Any future manual commit() calls should be mocked here as well.
    """
    def __init__(self, loop):
        self._loop = loop
        self.engine = None
        self._connection = None
        self._conn_present = Event()
        self._keep = None
        self._lock = Lock()
        self._done = Event()

    async def connect(self, host="localhost", port=3306, user="root",
                      password="", db="faf_test", minsize=1, maxsize=1):
        if self.engine is not None:
            raise ValueError("DB is already connected!")
        self.engine = await create_engine(
            host=host,
            port=port,
            user=user,
            password=password,
            db=db,
            autocommit=False,
            loop=self._loop,
            minsize=minsize,
            maxsize=maxsize,
            echo=True
        )
        self._keep = self._loop.create_task(self._keep_connection())
        await self._conn_present.wait()

    async def _keep_connection(self):
        async with self.engine.acquire() as conn:
            self._connection = conn
            self._conn_present.set()
            await self._done.wait()
            self._connection = None

    def acquire(self):
        return MockConnectionContext(self)

    async def close(self):
        if self.engine is None:
            return

        async with self._lock:
            self._done.set()
            await self._keep
            self.engine.close()
            await self.engine.wait_closed()
            self.engine = None


def autocontext(*auto_args):
    """
    Automatically initializes context managers for the scope of a test function.

    Only supports context managers that don't take any arguments, so anything
    that requires the `request` fixture won't work.
    """
    def decorate_test(test):
        original_argspec = inspect.getfullargspec(test)
        argspec = new_argspec(original_argspec, auto_args)

        if asyncio.iscoroutinefunction(test):
            @impersonate(test)
            @define_function_signature(test.__name__, test.__doc__, argspec)
            async def wrapped_test(*args, **kwargs):
                # Tell pytest to omit the body of this function from tracebacks
                __tracebackhide__ = True

                with contextlib.ExitStack() as stack:
                    async with contextlib.AsyncExitStack() as astack:
                        fixtures = []
                        for _, arg in zip(auto_args, args):
                            cm = arg()
                            if hasattr(cm, "__aexit__"):
                                fixtures.append(
                                    await astack.enter_async_context(cm)
                                )
                            else:
                                fixtures.append(
                                    stack.enter_context(cm)
                                )

                        return await test(
                            *tuple(itertools.chain(
                                fixtures,
                                args[len(auto_args):]
                            )),
                            **kwargs
                        )

            return wrapped_test
        else:
            @impersonate(test)
            @define_function_signature(test.__name__, test.__doc__, argspec)
            def wrapped_test(*args, **kwargs):
                # Tell pytest to omit the body of this function from tracebacks
                __tracebackhide__ = True

                with contextlib.ExitStack() as stack:
                    fixtures = [
                        stack.enter_context(arg())
                        for _, arg in zip(auto_args, args)
                    ]
                    return test(
                        *tuple(itertools.chain(
                            fixtures,
                            args[len(auto_args):]
                        )),
                        **kwargs
                    )

            return wrapped_test

    return decorate_test


def new_argspec(original_argspec, auto_args):
    """Make an updated argspec for the wrapped test."""
    replaced_args = {
        original_arg: auto_arg
        for original_arg, auto_arg in zip(
            original_argspec.args[:len(auto_args)],
            auto_args
        )
    }
    new_args = tuple(itertools.chain(
        auto_args,
        original_argspec.args[len(auto_args):]
    ))
    annots = {
        replaced_args.get(k) or k: v
        for k, v in original_argspec.annotations.items()
    }
    annots["return"] = None
    return original_argspec._replace(
        args=new_args,
        annotations=annots
    )
