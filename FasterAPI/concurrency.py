"""Concurrency engine for FasterAPI.

Designed for Python 3.13 first, with graceful degradation:

  Python 3.13+  →  Sub-interpreters with per-interpreter GIL (PEP 684/734)
                   Each worker gets its own GIL — true parallelism for
                   CPU-bound Python, no pickling, no process overhead.
                   This is the closest Python analog to Go goroutines.

  Python 3.12   →  Improved GIL with per-interpreter support partially
                   available. Falls back to ProcessPoolExecutor for
                   CPU-bound work, ThreadPoolExecutor for I/O.

  Python 3.11   →  ProcessPoolExecutor for CPU parallelism (pickle-based),
                   ThreadPoolExecutor for I/O-bound blocking calls.

  Python 3.10-  →  Same as 3.11 but with less efficient asyncio internals.
                   FasterAPI still works, but upgrading is recommended.

The public API is identical regardless of Python version:

    await run_in_subinterpreter(func, *args)   # CPU-bound
    await run_in_threadpool(func, *args)        # I/O-bound
    await run_in_executor(func, *args)          # process pool
"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from functools import partial
from typing import Any, Callable

# ───────────────────────────────────────────────────────────────────────
#  Version detection
# ───────────────────────────────────────────────────────────────────────

_PY_VERSION = sys.version_info
_PY313_PLUS = _PY_VERSION >= (3, 13)
_PY312_PLUS = _PY_VERSION >= (3, 12)
_PY311_PLUS = _PY_VERSION >= (3, 11)

# Detect available CPU cores for default pool sizing
_CPU_COUNT = os.cpu_count() or 4

# ───────────────────────────────────────────────────────────────────────
#  Shared pool singletons
# ───────────────────────────────────────────────────────────────────────

_process_pool: ProcessPoolExecutor | None = None
_thread_pool: ThreadPoolExecutor | None = None


def _get_process_pool() -> ProcessPoolExecutor:
    """Return the global process pool, lazily created."""
    global _process_pool
    if _process_pool is None:
        _process_pool = ProcessPoolExecutor(max_workers=_CPU_COUNT)
    return _process_pool


def _get_thread_pool() -> ThreadPoolExecutor:
    """Return the global thread pool, lazily created."""
    global _thread_pool
    if _thread_pool is None:
        # Python 3.13+ defaults to min(32, cpu+4); match that on older versions
        _thread_pool = ThreadPoolExecutor(max_workers=min(32, _CPU_COUNT + 4))
    return _thread_pool


# ───────────────────────────────────────────────────────────────────────
#  Core helpers
# ───────────────────────────────────────────────────────────────────────

def is_coroutine(func: Callable) -> bool:  # type: ignore[type-arg]
    """Return True if *func* is a coroutine function."""
    return inspect.iscoroutinefunction(func)


async def run_in_executor(func: Callable, *args: Any) -> Any:  # type: ignore[type-arg]
    """Run *func* in a process pool — bypasses the GIL via multiprocessing.

    Arguments must be picklable. For lighter-weight CPU parallelism on
    Python 3.13+, prefer ``run_in_subinterpreter``.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_process_pool(), partial(func, *args))


async def run_in_threadpool(func: Callable, *args: Any) -> Any:  # type: ignore[type-arg]
    """Run *func* in the shared thread pool — ideal for blocking I/O.

    On Python < 3.13, threads share a single GIL so this does NOT help
    with CPU-bound work. On 3.13+ with per-interpreter GIL, threads
    within the *same* interpreter still share one GIL.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_thread_pool(), partial(func, *args))


# ───────────────────────────────────────────────────────────────────────
#  Python 3.13+: Sub-interpreter pool (per-interpreter GIL)
# ───────────────────────────────────────────────────────────────────────
#
#  PEP 684 (Python 3.12) introduced per-interpreter GIL at the C level.
#  PEP 734 (Python 3.13) exposes it via the `interpreters` stdlib module.
#
#  Each sub-interpreter:
#    - Has its own GIL → true parallel execution of Python bytecode
#    - Has its own module state → no shared mutable globals
#    - Communicates via channels (memoryview, bytes) → no pickling
#    - Is ~100x lighter than a process → fast startup, low memory
#
#  This makes sub-interpreters the closest Python equivalent to
#  goroutines: lightweight, parallel, share-nothing by default.
# ───────────────────────────────────────────────────────────────────────

_HAS_INTERPRETERS = False
if _PY313_PLUS:
    try:
        import interpreters  # type: ignore[import-not-found]
        import interpreters.channels  # type: ignore[import-not-found]
        _HAS_INTERPRETERS = True
    except ImportError:
        pass

if _HAS_INTERPRETERS:

    class SubInterpreterPool:
        """Pool of Python 3.13+ sub-interpreters, each with its own GIL.

        True CPU-bound parallelism without process overhead::

            pool = SubInterpreterPool(max_workers=4)
            result = await pool.run(cpu_heavy, arg1, arg2)
            pool.shutdown()

        Or use the module-level convenience function::

            result = await run_in_subinterpreter(cpu_heavy, arg1, arg2)
        """

        def __init__(self, max_workers: int | None = None) -> None:
            self._max_workers = max_workers or _CPU_COUNT
            self._interpreters: list[Any] = []
            self._semaphore: asyncio.Semaphore | None = None
            self._initialized = False
            self._thread_pool = ThreadPoolExecutor(
                max_workers=self._max_workers,
            )

        def _ensure_initialized(self) -> None:
            if self._initialized:
                return
            for _ in range(self._max_workers):
                interp = interpreters.create()
                self._interpreters.append(interp)
            self._semaphore = asyncio.Semaphore(self._max_workers)
            self._initialized = True

        async def run(self, func: Callable, *args: Any) -> Any:  # type: ignore[type-arg]
            """Execute *func* in a sub-interpreter with its own GIL.

            The function is called via ``interp.call(func, *args)``.
            Arguments must be shareable across interpreters.
            """
            self._ensure_initialized()
            assert self._semaphore is not None
            async with self._semaphore:
                # Round-robin: pick the next free interpreter
                interp = self._interpreters[
                    id(asyncio.current_task()) % len(self._interpreters)
                ]
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    self._thread_pool,
                    partial(interp.call, func, *args),
                )

        def shutdown(self) -> None:
            """Destroy all sub-interpreters and the backing thread pool."""
            self._thread_pool.shutdown(wait=False)
            for interp in self._interpreters:
                try:
                    interp.close()
                except Exception:
                    pass
            self._interpreters.clear()
            self._initialized = False

# ───────────────────────────────────────────────────────────────────────
#  Fallback: ProcessPoolExecutor for CPU parallelism
# ───────────────────────────────────────────────────────────────────────
#
#  Used when the `interpreters` module is unavailable (Python < 3.14,
#  or 3.13 without the experimental stdlib module).
#  Same public API, ProcessPoolExecutor backend (pickle-based).
# ───────────────────────────────────────────────────────────────────────

if not _HAS_INTERPRETERS:

    class SubInterpreterPool:  # type: ignore[no-redef]
        """Fallback pool using ProcessPoolExecutor.

        Provides the same ``run()`` / ``shutdown()`` API as the
        sub-interpreter pool. Upgrade to a Python version with the
        ``interpreters`` module for true per-interpreter GIL support.
        """

        def __init__(self, max_workers: int | None = None) -> None:
            self._executor = ProcessPoolExecutor(
                max_workers=max_workers or _CPU_COUNT,
            )

        async def run(self, func: Callable, *args: Any) -> Any:  # type: ignore[type-arg]
            """Execute *func* in a worker process (pickle-based)."""
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                self._executor, partial(func, *args),
            )

        def shutdown(self) -> None:
            """Shut down the process pool."""
            self._executor.shutdown(wait=False)


# ───────────────────────────────────────────────────────────────────────
#  Global sub-interpreter pool singleton + convenience function
# ───────────────────────────────────────────────────────────────────────

_subinterp_pool: SubInterpreterPool | None = None


def _get_subinterp_pool(max_workers: int | None = None) -> SubInterpreterPool:
    """Return the global sub-interpreter pool, lazily created."""
    global _subinterp_pool
    if _subinterp_pool is None:
        _subinterp_pool = SubInterpreterPool(max_workers=max_workers)
    return _subinterp_pool


async def run_in_subinterpreter(func: Callable, *args: Any) -> Any:  # type: ignore[type-arg]
    """Execute *func* with maximum available parallelism.

    **Python 3.13+**: Runs in a sub-interpreter with its own GIL.
    True parallel execution, no pickling, ~100x lighter than a process.

    **Python 3.11–3.12**: Falls back to ``ProcessPoolExecutor``.
    Arguments must be picklable. Still achieves parallelism via
    multiprocessing.

    **Python < 3.11**: Same as 3.11 fallback with older asyncio internals.

    Usage::

        result = await run_in_subinterpreter(heavy_computation, n)
    """
    pool = _get_subinterp_pool()
    return await pool.run(func, *args)


# ───────────────────────────────────────────────────────────────────────
#  Event loop policy selection
# ───────────────────────────────────────────────────────────────────────
#
#  Python 3.13 ships with significant asyncio performance improvements
#  (PEP 703 prep, faster task creation). uvloop still helps on 3.13 but
#  the gap is smaller.
#
#  Strategy:
#    3.13+ → Try uvloop first (still fastest), fall back to stdlib
#    3.11+ → uvloop strongly recommended, fall back to stdlib
#    older  → uvloop if available, else stdlib
# ───────────────────────────────────────────────────────────────────────

def install_event_loop() -> str:
    """Install the fastest available event loop and return its name.

    Returns one of: ``"uvloop"``, ``"asyncio"``.
    """
    try:
        import uvloop
        if _PY312_PLUS:
            # uvloop.install() is deprecated on 3.12+; set the policy instead
            import asyncio
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        else:
            uvloop.install()
        return "uvloop"
    except ImportError:
        return "asyncio"
