"""Redis-backed HTTP response cache middleware (optional ``redis`` extra)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .middleware import BaseHTTPMiddleware
from .types import ASGIApp


class RedisCacheMiddleware(BaseHTTPMiddleware):
    """Cache **GET** responses (small bodies) in Redis.

    Skips caching when the client sends ``Cache-Control: no-cache`` or when the
    response status is not in *cacheable_statuses*. Suitable for idempotent JSON
    APIs; validate before caching authenticated routes.

    Requires ``redis>=5`` with ``redis.asyncio`` and ``pip install redis``.
    """

    def __init__(
        self,
        app: ASGIApp,
        redis_client: Any,
        *,
        ttl: int = 300,
        key_prefix: str = "fasterapi:http:",
        methods: tuple[str, ...] = ("GET",),
        cacheable_statuses: tuple[int, ...] = (200,),
        max_body_bytes: int = 1_048_576,
    ) -> None:
        super().__init__(app)
        self.redis = redis_client
        self.ttl = ttl
        self.key_prefix = key_prefix
        self.methods = {m.upper() for m in methods}
        self.cacheable_statuses = cacheable_statuses
        self.max_body_bytes = max_body_bytes

    def _cache_key(self, scope: dict[str, Any]) -> str:
        path = scope.get("path", "/")
        qs = scope.get("query_string", b"").decode("latin-1")
        raw = f"{path}?{qs}".encode()
        digest = hashlib.sha256(raw).hexdigest()
        return f"{self.key_prefix}{digest}"

    async def dispatch(
        self,
        scope: dict[str, Any],
        receive: ASGIApp,
        send: ASGIApp,
    ) -> None:
        if scope["method"].upper() not in self.methods:
            await self.app(scope, receive, send)
            return

        headers_in = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if "no-cache" in headers_in.get("cache-control", "").lower():
            await self.app(scope, receive, send)
            return

        cache_key = self._cache_key(scope)
        try:
            cached = await self.redis.get(cache_key)
        except Exception:
            await self.app(scope, receive, send)
            return

        if cached:
            try:
                payload = json.loads(cached)
                status = int(payload["status"])
                res_headers = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in payload["headers"]]
                body = bytes.fromhex(payload["body_hex"])
            except (KeyError, ValueError, TypeError):
                await self.app(scope, receive, send)
                return

            await send({"type": "http.response.start", "status": status, "headers": res_headers})
            await send({"type": "http.response.body", "body": body})
            return

        start_msg: dict[str, Any] | None = None
        body_parts: list[bytes] = []

        async def capturing_send(message: dict[str, Any]) -> None:
            nonlocal start_msg
            if message["type"] == "http.response.start":
                start_msg = message
            elif message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))
            await send(message)

        await self.app(scope, receive, capturing_send)

        if start_msg is None:
            return
        status = int(start_msg.get("status", 200))
        if status not in self.cacheable_statuses:
            return
        full = b"".join(body_parts)
        if len(full) > self.max_body_bytes:
            return
        raw_headers = start_msg.get("headers", [])
        headers_list = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in raw_headers]
        payload_dict = {"status": status, "headers": headers_list, "body_hex": full.hex()}
        payload_str = json.dumps(payload_dict)
        try:
            await self.redis.set(cache_key, payload_str, ex=self.ttl)
        except Exception:
            return
