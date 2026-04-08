"""Concurrency utilities for FasterAPI.

Provides thread pool, process pool, and Python 3.13+ sub-interpreter
execution. Sub-interpreters each have their own GIL, enabling true
parallelism for CPU-bound Python code — the closest Python equivalent
to goroutines.

On Python < 3.13, ``run_in_subinterpreter`` falls back to a
``ProcessPoolExecutor``.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from functools import partial
from typing import Any, Callable

_process_pool: ProcessPoolExecutor | None = None
_thread_pool: ThreadPoolExecutor | None = None

# Python 3.13+ sub-interpreter support (PEP 734)
_HAS_SUBINTERPRETERS = sys.version_info >= (3, 13)


def _get_process_pool() -> ProcessPoolExecutor:
    """Return the global process pool, creating it on first use."""
    global _process_pool
    if _process_pool is None:
        _process_pool = ProcessPoolExecutor()
    return _process_pool


def _get_thread_pool() -> ThreadPoolExecutor:
    """Return the global thread pool, creating it on first use."""
    global _thread_pool
    if _thread_pool is None:
        _thread_pool = ThreadPoolExecutor()
    return _thread_pool


def is_coroutine(func: Callable) -> bool:  # type: ignore[type-arg]
    """Return True if the given callable is a coroutine function."""
    return inspect.iscoroutinefunction(func)


async def run_in_executor(func: Callable, *args: Any) -> Any:  # type: ignore[type-arg]
    """Run a sync function in a process pool executor.

    Uses ``ProcessPoolExecutor`` to bypass the GIL for CPU-bound work.
    Consider ``run_in_subinterpreter`` on Python 3.13+ for lighter-weight
    parallelism without pickling overhead.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_process_pool(), partial(func, *args))


async def run_in_threadpool(func: Callable, *args: Any) -> Any:  # type: ignore[type-arg]
    """Run a sync function in a thread pool executor.

    Suitable for I/O-bound blocking operations (file I/O, legacy DB
    drivers). The function still shares the main GIL on Python < 3.13.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_thread_pool(), partial(func, *args))


# ---------------------------------------------------------------------------
# Python 3.13+ sub-interpreter support
# ---------------------------------------------------------------------------
# Sub-interpreters each get their own GIL (PEP 684 / PEP 734), enabling
# true parallelism for CPU-bound Python code without the serialization
# overhead of multiprocessing (no pickling, shared-nothing by default).
#
# This is the closest Python analog to Go's goroutines — lightweight
# execution contexts that run truly in parallel.
#
# On Python < 3.13 we transparently fall back to ProcessPoolExecutor.
# ---------------------------------------------------------------------------

if _HAS_SUBINTERPRETERS:
    # These imports are only available on Python 3.13+
    import interpreters  # type: ignore[import-not-found]

    class SubInterpreterPool:
        """Pool of sub-interpreters, each with its own GIL.

        Each sub-interpreter is a lightweight Python execution context
        that runs with its own Global Interpreter Lock, enabling true
        CPU parallelism without process overhead.

        Usage::

            pool = SubInterpreterPool(max_workers=4)
            result = await pool.run(cpu_heavy_func, arg1, arg2)
            pool.shutdown()
        """

        def __init__(self, max_workers: int = 4) -> None:
            self._max_workers = max_workers
            self._interpreters: list[Any] = []
            self._available: asyncio.Queue[Any] = asyncio.Queue()
            self._initialized = False

        def _ensure_initialized(self) -> None:
            """Lazily create sub-interpreters on first use."""
            if self._initialized:
                return
            for _ in range(self._max_workers):
                interp = interpreters.create()
                self._interpreters.append(interp)
                self._available.put_nowait(interp)
            self._initialized = True

        async def run(self, func: Callable, *args: Any) -> Any:  # type: ignore[type-arg]
            """Execute *func* in a sub-interpreter with its own GIL.

            The function and arguments must be shareable across
            interpreters (simple types, bytes, etc.).
            """
            self._ensure_initialized()
            interp = await self._available.get()
            loop = asyncio.get_running_loop()
            try:
                result = await loop.run_in_executor(
                    None,
                    partial(self._exec_in_interp, interp, func, *args),
                )
                return result
            finally:
                self._available.put_nowait(interp)

        @staticmethod
        def _exec_in_interp(interp: Any, func: Callable, *args: Any) -> Any:  # type: ignore[type-arg]
            """Run the function inside the given sub-interpreter."""
            # On 3.13+, interpreters.run() executes code with its own GIL
            return interp.call(func, *args)

        def shutdown(self) -> None:
            """Destroy all sub-interpreters in the pool."""
            for interp in self._interpreters:
                try:
                    interp.close()
                except Exception:
                    pass
            self._interpreters.clear()
            self._initialized = False

    _subinterp_pool: SubInterpreterPool | None = None

    def _get_subinterp_pool(max_workers: int = 4) -> SubInterpreterPool:
        """Return the global sub-interpreter pool, creating it on first use."""
        global _subinterp_pool
        if _subinterp_pool is None:
            _subinterp_pool = SubInterpreterPool(max_workers=max_workers)
        return _subinterp_pool

    async def run_in_subinterpreter(func: Callable, *args: Any) -> Any:  # type: ignore[type-arg]
        """Execute *func* in a sub-interpreter with its own GIL.

        Each sub-interpreter has an independent GIL, enabling true
        CPU-bound parallelism — the closest Python equivalent to
        goroutines. No pickling required (unlike multiprocessing).

        Falls back to ``ProcessPoolExecutor`` on Python < 3.13.
        """
        pool = _get_subinterp_pool()
        return await pool.run(func, *args)

else:
    # Fallback for Python < 3.13: use ProcessPoolExecutor
    class SubInterpreterPool:  # type: ignore[no-redef]
        """Fallback pool using ProcessPoolExecutor on Python < 3.13.

        Provides the same API as the sub-interpreter pool but uses
        multiprocessing under the hood. Upgrade to Python 3.13+ for
        true sub-interpreter support with per-interpreter GIL.
        """

        def __init__(self, max_workers: int = 4) -> None:
            self._executor = ProcessPoolExecutor(max_workers=max_workers)

        async def run(self, func: Callable, *args: Any) -> Any:  # type: ignore[type-arg]
            """Execute *func* in a worker process (fallback)."""
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                self._executor, partial(func, *args),
            )

        def shutdown(self) -> None:
            """Shut down the process pool."""
            self._executor.shutdown(wait=False)

    _subinterp_pool: SubInterpreterPool | None = None  # type: ignore[no-redef]

    def _get_subinterp_pool(max_workers: int = 4) -> SubInterpreterPool:
        """Return the global fallback pool, creating it on first use."""
        global _subinterp_pool
        if _subinterp_pool is None:
            _subinterp_pool = SubInterpreterPool(max_workers=max_workers)
        return _subinterp_pool

    async def run_in_subinterpreter(func: Callable, *args: Any) -> Any:  # type: ignore[type-arg]
        """Execute *func* in a separate process (Python < 3.13 fallback).

        On Python 3.13+, this uses true sub-interpreters with
        per-interpreter GIL. On older versions, it falls back to
        ``ProcessPoolExecutor``.
        """
        pool = _get_subinterp_pool()
        return await pool.run(func, *args)
