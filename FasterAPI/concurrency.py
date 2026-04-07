from __future__ import annotations

import asyncio
import inspect
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from functools import partial
from typing import Any, Callable

_process_pool: ProcessPoolExecutor | None = None
_thread_pool: ThreadPoolExecutor | None = None


def _get_process_pool() -> ProcessPoolExecutor:
    global _process_pool
    if _process_pool is None:
        _process_pool = ProcessPoolExecutor()
    return _process_pool


def _get_thread_pool() -> ThreadPoolExecutor:
    global _thread_pool
    if _thread_pool is None:
        _thread_pool = ThreadPoolExecutor()
    return _thread_pool


def is_coroutine(func: Callable) -> bool:
    return inspect.iscoroutinefunction(func)


async def run_in_executor(func: Callable, *args: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_process_pool(), partial(func, *args))


async def run_in_threadpool(func: Callable, *args: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_thread_pool(), partial(func, *args))
