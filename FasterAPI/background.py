from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from .concurrency import is_coroutine


class BackgroundTask:
    """A single background task to be executed after a response is sent."""

    __slots__ = ("func", "args", "kwargs")

    def __init__(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        self.func = func
        self.args = args
        self.kwargs = kwargs

    async def run(self) -> None:
        """Execute the background task."""
        if is_coroutine(self.func):
            await self.func(*self.args, **self.kwargs)
        else:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._run_sync)

    def _run_sync(self) -> None:
        self.func(*self.args, **self.kwargs)


class BackgroundTasks:
    """A collection of background tasks to be executed after a response is sent."""

    def __init__(self) -> None:
        self._tasks: list[BackgroundTask] = []

    def add_task(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Add a new background task to the collection."""
        self._tasks.append(BackgroundTask(func, *args, **kwargs))

    async def run(self) -> None:
        """Execute all background tasks sequentially."""
        for task in self._tasks:
            await task.run()
