"""Concurrency helpers (thread pool, process pool fallbacks)."""

import pytest

from FasterAPI import concurrency as c


def _cpu_add_one(x: int) -> int:
    return x + 1


def _work_double(x: int) -> int:
    return x * 2


def test_is_coroutine():
    async def acoro():
        return 1

    def sync():
        return 2

    assert c.is_coroutine(acoro) is True
    assert c.is_coroutine(sync) is False


@pytest.mark.asyncio
async def test_run_in_threadpool():
    def blocking() -> str:
        return "ok"

    assert await c.run_in_threadpool(blocking) == "ok"


@pytest.mark.asyncio
async def test_run_in_executor_runs():
    assert await c.run_in_executor(_cpu_add_one, 41) == 42


@pytest.mark.asyncio
async def test_run_in_subinterpreter_or_process():
    assert await c.run_in_subinterpreter(_work_double, 21) == 42


def test_install_event_loop_returns_string():
    name = c.install_event_loop()
    assert name in ("uvloop", "asyncio")
