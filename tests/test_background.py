"""Background task execution."""

import pytest
from FasterAPI.background import BackgroundTask, BackgroundTasks


@pytest.mark.asyncio
async def test_background_task_sync():
    out: list[int] = []

    def work(x: int) -> None:
        out.append(x)

    t = BackgroundTask(work, 42)
    await t.run()
    assert out == [42]


@pytest.mark.asyncio
async def test_background_task_async():
    out: list[str] = []

    async def work(msg: str) -> None:
        out.append(msg)

    t = BackgroundTask(work, "hi")
    await t.run()
    assert out == ["hi"]


@pytest.mark.asyncio
async def test_background_tasks_sequential():
    order: list[str] = []

    def a() -> None:
        order.append("a")

    async def b() -> None:
        order.append("b")

    bg = BackgroundTasks()
    bg.add_task(a)
    bg.add_task(b)
    await bg.run()
    assert order == ["a", "b"]
