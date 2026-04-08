from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any, Callable, Generator

import httpx

from .websocket import WebSocket, WebSocketDisconnect


class _WebSocketSession:
    """Test WebSocket session that communicates through in-memory queues."""

    def __init__(self) -> None:
        self._send_queue: asyncio.Queue[dict] = asyncio.Queue()
        self._receive_queue: asyncio.Queue[dict] = asyncio.Queue()
        self._accepted = False
        self._closed = False

    async def _asgi_receive(self) -> dict:
        return await self._receive_queue.get()

    async def _asgi_send(self, message: dict) -> None:
        await self._send_queue.put(message)

    def send_text(self, data: str) -> None:
        self._receive_queue.put_nowait({"type": "websocket.receive", "text": data})

    def send_bytes(self, data: bytes) -> None:
        self._receive_queue.put_nowait({"type": "websocket.receive", "bytes": data})

    def send_json(self, data: Any) -> None:
        import msgspec.json
        self.send_text(msgspec.json.encode(data).decode())

    def receive_text(self) -> str:
        msg = self._drain_one()
        return str(msg.get("text", ""))

    def receive_bytes(self) -> bytes:
        msg = self._drain_one()
        return bytes(msg.get("bytes", b""))

    def receive_json(self) -> Any:
        import msgspec.json
        text = self.receive_text()
        return msgspec.json.decode(text.encode())

    def close(self, code: int = 1000) -> None:
        self._receive_queue.put_nowait({"type": "websocket.disconnect", "code": code})
        self._closed = True

    def _drain_one(self) -> dict:
        """Get the next message from the send queue (blocks briefly)."""
        try:
            msg = self._send_queue.get_nowait()
        except asyncio.QueueEmpty:
            raise RuntimeError("No message available from server")
        if msg.get("type") == "websocket.accept":
            self._accepted = True
            return self._drain_one()
        if msg.get("type") == "websocket.close":
            self._closed = True
            raise WebSocketDisconnect(msg.get("code", 1000))
        return msg


class TestClient:
    """Synchronous test client for FasterAPI applications.

    Wraps ASGI app with httpx.ASGITransport for HTTP testing.
    Provides websocket_connect() for WebSocket testing.
    """

    __test__ = False  # Prevent pytest collection

    def __init__(
        self,
        app: Callable,
        base_url: str = "http://testserver",
    ) -> None:
        self.app = app
        self.base_url = base_url
        self._transport = httpx.ASGITransport(app=app)
        self._client = httpx.AsyncClient(
            transport=self._transport,
            base_url=base_url,
        )

    def __enter__(self) -> TestClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self._run(self._client.aclose())

    def _run(self, coro: Any) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return asyncio.run(coro)

    # --- HTTP methods ---

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send a GET request."""
        result: httpx.Response = self._run(self._client.get(url, **kwargs))
        return result

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send a POST request."""
        result: httpx.Response = self._run(self._client.post(url, **kwargs))
        return result

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send a PUT request."""
        result: httpx.Response = self._run(self._client.put(url, **kwargs))
        return result

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send a DELETE request."""
        result: httpx.Response = self._run(self._client.delete(url, **kwargs))
        return result

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send a PATCH request."""
        result: httpx.Response = self._run(self._client.patch(url, **kwargs))
        return result

    def options(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send an OPTIONS request."""
        result: httpx.Response = self._run(self._client.options(url, **kwargs))
        return result

    def head(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send a HEAD request."""
        result: httpx.Response = self._run(self._client.head(url, **kwargs))
        return result

    # --- WebSocket ---

    @contextmanager
    def websocket_connect(
        self,
        path: str,
        headers: dict[str, str] | None = None,
        query_string: str = "",
    ) -> Generator[_WebSocketSession, None, None]:
        """Context manager for testing WebSocket endpoints."""
        session = _WebSocketSession()

        scope = {
            "type": "websocket",
            "path": path,
            "headers": [
                (k.lower().encode(), v.encode())
                for k, v in (headers or {}).items()
            ],
            "query_string": query_string.encode() if query_string else b"",
            "client": ("testclient", 0),
        }

        async def run_ws() -> None:
            await self.app(scope, session._asgi_receive, session._asgi_send)

        loop = asyncio.new_event_loop()
        task = loop.create_task(run_ws())

        # Drive the loop briefly to let the handler start and accept
        def _step() -> None:
            loop.run_until_complete(asyncio.sleep(0))

        _step()

        try:
            yield session
        finally:
            if not session._closed:
                session.close()
            # Drain remaining events
            for _ in range(100):
                try:
                    loop.run_until_complete(asyncio.wait_for(asyncio.shield(task), timeout=0.05))
                    break
                except (asyncio.TimeoutError, Exception):
                    break
            loop.close()
