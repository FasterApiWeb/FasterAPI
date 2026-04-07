from __future__ import annotations

import asyncio
from typing import Any, Callable

from .concurrency import is_coroutine


class BackgroundTask:
    __slots__ = ("func", "args", "kwargs")

    def __init__(self, func: Callable, *args: Any, **kwargs: Any) -> None:
        self.func = func
        self.args = args
        self.kwargs = kwargs

    async def run(self) -> None:
        if is_coroutine(self.func):
            await self.func(*self.args, **self.kwargs)
        else:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._run_sync)

    def _run_sync(self) -> None:
        self.func(*self.args, **self.kwargs)


class BackgroundTasks:
    def __init__(self) -> None:
        self._tasks: list[BackgroundTask] = []

    def add_task(self, func: Callable, *args: Any, **kwargs: Any) -> None:
        self._tasks.append(BackgroundTask(func, *args, **kwargs))

    async def run(self) -> None:
        for task in self._tasks:
            await task.run()
