from __future__ import annotations

import asyncio
import gzip
from typing import Any, Callable, Sequence


class BaseHTTPMiddleware:
    """Base class for HTTP middleware that wraps an ASGI application."""

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        await self.dispatch(scope, receive, send)

    async def dispatch(
        self, scope: dict, receive: Callable, send: Callable,
    ) -> None:
        """Process the request. Override this method in subclasses."""
        async def call_next() -> None:
            await self.app(scope, receive, send)

        await call_next()


class CORSMiddleware(BaseHTTPMiddleware):
    """Middleware that handles Cross-Origin Resource Sharing (CORS) headers."""

    def __init__(
        self,
        app: Callable,
        *,
        allow_origins: Sequence[str] = ("*",),
        allow_methods: Sequence[str] = ("*",),
        allow_headers: Sequence[str] = ("*",),
        allow_credentials: bool = False,
        max_age: int = 600,
        expose_headers: Sequence[str] = (),
    ) -> None:
        super().__init__(app)
        self.allow_origins = set(allow_origins)
        self.allow_methods = set(allow_methods)
        self.allow_headers = set(allow_headers)
        self.allow_credentials = allow_credentials
        self.max_age = max_age
        self.expose_headers = set(expose_headers)
        self.allow_all_origins = "*" in self.allow_origins
        self.allow_all_methods = "*" in self.allow_methods
        self.allow_all_headers = "*" in self.allow_headers

    async def dispatch(
        self, scope: dict, receive: Callable, send: Callable,
    ) -> None:
        """Handle CORS preflight requests and inject CORS headers into responses."""
        headers_raw: list[tuple[bytes, bytes]] = scope.get("headers", [])
        request_headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in headers_raw}
        origin = request_headers.get("origin")
        method = scope.get("method", "GET")

        # Preflight
        if method == "OPTIONS" and "access-control-request-method" in request_headers:
            await self._preflight_response(send, origin, request_headers)
            return

        # Normal request — intercept send to inject CORS headers
        cors_headers = self._build_cors_headers(origin)

        async def send_with_cors(message: dict) -> None:
            if message["type"] == "http.response.start":
                existing = list(message.get("headers", []))
                existing.extend(cors_headers)
                message = {**message, "headers": existing}
            await send(message)

        await self.app(scope, receive, send_with_cors)

    def _origin_allowed(self, origin: str | None) -> bool:
        if origin is None:
            return False
        if self.allow_all_origins:
            return True
        return origin in self.allow_origins

    def _build_cors_headers(self, origin: str | None) -> list[tuple[bytes, bytes]]:
        if not self._origin_allowed(origin):
            return []

        headers: list[tuple[bytes, bytes]] = []
        if self.allow_all_origins and not self.allow_credentials:
            headers.append((b"access-control-allow-origin", b"*"))
        elif origin:
            headers.append((b"access-control-allow-origin", origin.encode("latin-1")))
            headers.append((b"vary", b"Origin"))

        if self.allow_credentials:
            headers.append((b"access-control-allow-credentials", b"true"))

        if self.expose_headers:
            headers.append((
                b"access-control-expose-headers",
                ", ".join(self.expose_headers).encode("latin-1"),
            ))
        return headers

    async def _preflight_response(
        self,
        send: Callable,
        origin: str | None,
        request_headers: dict[str, str],
    ) -> None:
        headers: list[tuple[bytes, bytes]] = []

        if self._origin_allowed(origin):
            if self.allow_all_origins and not self.allow_credentials:
                headers.append((b"access-control-allow-origin", b"*"))
            elif origin:
                headers.append((b"access-control-allow-origin", origin.encode("latin-1")))
                headers.append((b"vary", b"Origin"))

            # Methods
            if self.allow_all_methods:
                req_method = request_headers.get("access-control-request-method", "")
                headers.append((b"access-control-allow-methods", req_method.encode("latin-1")))
            else:
                headers.append((
                    b"access-control-allow-methods",
                    ", ".join(self.allow_methods).encode("latin-1"),
                ))

            # Headers
            if self.allow_all_headers:
                req_headers = request_headers.get("access-control-request-headers", "")
                headers.append((b"access-control-allow-headers", req_headers.encode("latin-1")))
            else:
                headers.append((
                    b"access-control-allow-headers",
                    ", ".join(self.allow_headers).encode("latin-1"),
                ))

            if self.allow_credentials:
                headers.append((b"access-control-allow-credentials", b"true"))

            headers.append((b"access-control-max-age", str(self.max_age).encode()))

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": headers,
        })
        await send({"type": "http.response.body", "body": b""})


class GZipMiddleware(BaseHTTPMiddleware):
    """Middleware that compresses responses using gzip when the client supports it."""

    def __init__(self, app: Callable, *, minimum_size: int = 1000) -> None:
        super().__init__(app)
        self.minimum_size = minimum_size

    async def dispatch(
        self, scope: dict, receive: Callable, send: Callable,
    ) -> None:
        """Compress the response body with gzip if it exceeds the minimum size."""
        headers_raw: list[tuple[bytes, bytes]] = scope.get("headers", [])
        accept_encoding = ""
        for k, v in headers_raw:
            if k.decode("latin-1").lower() == "accept-encoding":
                accept_encoding = v.decode("latin-1")
                break

        if "gzip" not in accept_encoding.lower():
            await self.app(scope, receive, send)
            return

        # Collect response to potentially compress
        initial_message: dict | None = None
        body_parts: list[bytes] = []

        async def buffered_send(message: dict) -> None:
            nonlocal initial_message
            if message["type"] == "http.response.start":
                initial_message = message
            elif message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))
                if not message.get("more_body", False):
                    # All body collected — decide whether to compress
                    full_body = b"".join(body_parts)
                    if len(full_body) >= self.minimum_size and initial_message is not None:
                        compressed = gzip.compress(full_body)
                        headers = list(initial_message.get("headers", []))
                        headers.append((b"content-encoding", b"gzip"))
                        headers.append((b"vary", b"Accept-Encoding"))
                        # Update content-length
                        headers = [
                            (k, v) for k, v in headers
                            if k.lower() != b"content-length"
                        ]
                        headers.append((b"content-length", str(len(compressed)).encode()))
                        await send({**initial_message, "headers": headers})
                        await send({"type": "http.response.body", "body": compressed})
                    else:
                        if initial_message is not None:
                            await send(initial_message)
                        await send({"type": "http.response.body", "body": full_body})

        await self.app(scope, receive, buffered_send)


class TrustedHostMiddleware(BaseHTTPMiddleware):
    """Middleware that validates the Host header against a list of allowed hosts."""

    def __init__(
        self, app: Callable, *, allowed_hosts: Sequence[str] = ("*",),
    ) -> None:
        super().__init__(app)
        self.allowed_hosts = set(allowed_hosts)
        self.allow_all = "*" in self.allowed_hosts

    async def dispatch(
        self, scope: dict, receive: Callable, send: Callable,
    ) -> None:
        if self.allow_all:
            await self.app(scope, receive, send)
            return

        headers_raw: list[tuple[bytes, bytes]] = scope.get("headers", [])
        host = ""
        for k, v in headers_raw:
            if k.decode("latin-1").lower() == "host":
                host = v.decode("latin-1").split(":")[0]
                break

        if host not in self.allowed_hosts:
            await send({
                "type": "http.response.start",
                "status": 400,
                "headers": [(b"content-type", b"text/plain")],
            })
            await send({
                "type": "http.response.body",
                "body": b"Invalid host header",
            })
            return

        await self.app(scope, receive, send)


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Middleware that redirects all HTTP requests to HTTPS."""

    async def dispatch(
        self, scope: dict, receive: Callable, send: Callable,
    ) -> None:
        if scope.get("scheme", "http") == "https":
            await self.app(scope, receive, send)
            return

        # Build redirect URL
        headers_raw: list[tuple[bytes, bytes]] = scope.get("headers", [])
        host = "localhost"
        for k, v in headers_raw:
            if k.decode("latin-1").lower() == "host":
                host = v.decode("latin-1")
                break

        path = scope.get("path", "/")
        qs = scope.get("query_string", b"")
        url = f"https://{host}{path}"
        if qs:
            url += f"?{qs.decode('latin-1')}"

        await send({
            "type": "http.response.start",
            "status": 301,
            "headers": [
                (b"location", url.encode("latin-1")),
                (b"content-type", b"text/plain"),
            ],
        })
        await send({"type": "http.response.body", "body": b"Redirecting to HTTPS"})
