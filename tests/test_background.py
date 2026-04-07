import asyncio

import pytest

from FasterAPI.background import BackgroundTask, BackgroundTasks
from FasterAPI.dependencies import _resolve_handler
from FasterAPI.request import Request


# --------------- helpers ---------------

def _make_request(
    *,
    method: str = "GET",
    path: str = "/",
    headers: list[tuple[bytes, bytes]] | None = None,
    query_string: bytes = b"",
) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers or [],
        "query_string": query_string,
        "path_params": {},
        "client": ("127.0.0.1", 8000),
    }
    called = False

    async def receive():
        nonlocal called
        if not called:
            called = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


# ==============================
#  BackgroundTask unit tests
# ==============================

class TestBackgroundTask:
    @pytest.mark.asyncio
    async def test_async_task(self):
        results = []

        async def work(value):
            results.append(value)

        task = BackgroundTask(work, "hello")
        await task.run()
        assert results == ["hello"]

    @pytest.mark.asyncio
    async def test_sync_task(self):
        results = []

        def work(value):
            results.append(value)

        task = BackgroundTask(work, "sync")
        await task.run()
        assert results == ["sync"]

    @pytest.mark.asyncio
    async def test_task_with_kwargs(self):
        results = {}

        async def work(key, value="default"):
            results[key] = value

        task = BackgroundTask(work, "k", value="v")
        await task.run()
        assert results == {"k": "v"}


# ==============================
#  BackgroundTasks unit tests
# ==============================

class TestBackgroundTasks:
    @pytest.mark.asyncio
    async def test_add_and_run_multiple(self):
        order = []

        async def task_a():
            order.append("a")

        async def task_b():
            order.append("b")

        bg = BackgroundTasks()
        bg.add_task(task_a)
        bg.add_task(task_b)
        await bg.run()
        assert order == ["a", "b"]

    @pytest.mark.asyncio
    async def test_empty_run(self):
        bg = BackgroundTasks()
        await bg.run()  # should not raise

    @pytest.mark.asyncio
    async def test_mixed_sync_async(self):
        results = []

        async def async_work():
            results.append("async")

        def sync_work():
            results.append("sync")

        bg = BackgroundTasks()
        bg.add_task(async_work)
        bg.add_task(sync_work)
        await bg.run()
        assert results == ["async", "sync"]


# ==============================
#  DI injection tests
# ==============================

class TestBackgroundTasksInjection:
    @pytest.mark.asyncio
    async def test_inject_and_add_task(self):
        executed = []

        async def send_email(to: str):
            executed.append(to)

        async def handler(bg: BackgroundTasks):
            bg.add_task(send_email, "user@example.com")
            return {"status": "ok"}

        req = _make_request()
        result, bg_tasks = await _resolve_handler(handler, req, {})
        assert result == {"status": "ok"}
        assert bg_tasks is not None
        await bg_tasks.run()
        assert executed == ["user@example.com"]

    @pytest.mark.asyncio
    async def test_no_tasks_returns_none(self):
        async def handler(bg: BackgroundTasks):
            return {"status": "ok"}

        req = _make_request()
        result, bg_tasks = await _resolve_handler(handler, req, {})
        assert result == {"status": "ok"}
        assert bg_tasks is None

    @pytest.mark.asyncio
    async def test_handler_without_bg_returns_none(self):
        async def handler():
            return {"status": "ok"}

        req = _make_request()
        result, bg_tasks = await _resolve_handler(handler, req, {})
        assert result == {"status": "ok"}
        assert bg_tasks is None

    @pytest.mark.asyncio
    async def test_multiple_tasks_run_in_order(self):
        order = []

        async def handler(bg: BackgroundTasks):
            bg.add_task(lambda: order.append(1))
            bg.add_task(lambda: order.append(2))
            bg.add_task(lambda: order.append(3))
            return {"queued": 3}

        req = _make_request()
        result, bg_tasks = await _resolve_handler(handler, req, {})
        assert result == {"queued": 3}
        await bg_tasks.run()
        assert order == [1, 2, 3]


# ==============================
#  Full app integration test
# ==============================

class TestBackgroundTasksAppIntegration:
    @pytest.mark.asyncio
    async def test_tasks_run_after_response(self):
        from FasterAPI.app import Faster

        executed = []
        app = Faster(openapi_url=None, docs_url=None, redoc_url=None)

        @app.post("/notify")
        async def notify(bg: BackgroundTasks):
            bg.add_task(lambda: executed.append("done"))
            return {"sent": True}

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/notify",
            "headers": [],
            "query_string": b"",
            "path_params": {},
            "client": ("127.0.0.1", 8000),
        }
        body_sent = False

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        await app._handle_http(scope, receive, send)

        # Response was sent
        assert sent_messages[0]["type"] == "http.response.start"
        assert sent_messages[0]["status"] == 200
        # Background task ran after response
        assert executed == ["done"]
