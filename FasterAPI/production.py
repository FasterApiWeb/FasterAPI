"""Production-oriented middleware: rate limits, request correlation IDs, DB pool binding."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

from .middleware import BaseHTTPMiddleware
from .types import ASGIApp


class DatabasePoolMiddleware(BaseHTTPMiddleware):
    """Attach a shared pool/engine object to ``scope["state"]`` for handlers.

    Typical usage with SQLAlchemy::

        engine = create_async_engine(url, pool_size=20)

        app.add_middleware(DatabasePoolMiddleware, pool=engine, state_key="engine")

        def get_engine(request: Request):
            return request.state["engine"]

    For **asyncpg**, pass the ``asyncpg.Pool`` instance as ``pool``.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        pool: Any,
        state_key: str = "db_pool",
    ) -> None:
        super().__init__(app)
        self.pool = pool
        self.state_key = state_key

    async def dispatch(
        self,
        scope: dict[str, Any],
        receive: ASGIApp,
        send: ASGIApp,
    ) -> None:
        scope.setdefault("state", {})[self.state_key] = self.pool
        await self.app(scope, receive, send)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Ensure each request has ``X-Request-ID`` (generate or propagate).

    The ID is stored in ``scope["state"]["request_id"]`` (also available as
    ``request.state["request_id"]``).
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        header_name: str = "x-request-id",
        outgoing_header_name: str = "x-request-id",
        generator: Callable[[], str] | None = None,
    ) -> None:
        super().__init__(app)
        self.header_name = header_name.lower()
        self.outgoing_header_name = outgoing_header_name.lower()
        self.generator = generator or (lambda: uuid.uuid4().hex)

    async def dispatch(
        self,
        scope: dict[str, Any],
        receive: ASGIApp,
        send: ASGIApp,
    ) -> None:
        raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        incoming = ""
        for k, v in raw_headers:
            if k.decode("latin-1").lower() == self.header_name:
                incoming = v.decode("latin-1").strip()
                break

        rid = incoming or self.generator()
        scope.setdefault("state", {})["request_id"] = rid

        async def send_with_header(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                keys = {x[0].lower() for x in headers}
                out_key = self.outgoing_header_name.encode("latin-1")
                if out_key not in keys:
                    headers.append((out_key, rid.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_header)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple sliding-window rate limit per client IP (in-memory).

    Not suitable for multi-process deployments without a shared store—use Redis
    etc. for horizontal scale. For single-worker or development this is enough.

    ``client`` from ASGI scope is used unless ``forwarded_for_header`` is set and
    the header exists (first hop).
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        requests_per_minute: int = 120,
        window_seconds: float = 60.0,
        forwarded_for_header: str | None = None,
    ) -> None:
        super().__init__(app)
        if requests_per_minute < 1:
            raise ValueError("requests_per_minute must be >= 1")
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self.forwarded_for_header = forwarded_for_header.lower() if forwarded_for_header else None
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _client_key(self, scope: dict[str, Any]) -> str:
        if self.forwarded_for_header:
            for k, v in scope.get("headers", []):
                if k.decode("latin-1").lower() == self.forwarded_for_header:
                    first = v.decode("latin-1").split(",")[0].strip()
                    if first:
                        return first
                    break
        client = scope.get("client")
        return client[0] if client else "unknown"

    async def dispatch(
        self,
        scope: dict[str, Any],
        receive: ASGIApp,
        send: ASGIApp,
    ) -> None:
        key = self._client_key(scope)
        now = time.monotonic()
        cutoff = now - self.window_seconds
        dq = self._hits[key]
        while dq and dq[0] < cutoff:
            dq.popleft()

        if len(dq) >= self.requests_per_minute:
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"retry-after", b"60"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": b'{"detail":"Too Many Requests"}'})
            return

        dq.append(now)
        await self.app(scope, receive, send)
