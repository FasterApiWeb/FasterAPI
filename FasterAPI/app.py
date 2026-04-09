"""Core Faster application class — the ASGI entry point.

Optimisations over a naïve implementation:
  - Handler signatures are compiled once at route registration
  - Middleware chain is built once and cached
  - JSON responses use msgspec.json.encode (Rust-backed, zero-copy)
  - Common response path (dict → JSON bytes) avoids Response object overhead
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Sequence

import msgspec.json

from .concurrency import install_event_loop
from .dependencies import _resolve_handler, compile_handler
from .exceptions import (
    HTTPException,
    RequestValidationError,
    _default_http_exception_handler,
    _default_validation_exception_handler,
)
from .openapi.generator import generate_openapi
from .openapi.ui import redoc_html, swagger_ui_html
from .request import Request
from .response import HTMLResponse, JSONResponse, Response
from .router import RadixRouter
from .websocket import WebSocket

__all__ = ["Faster"]

_event_loop = install_event_loop()

# Pre-encode common header values to avoid repeated bytes() calls
_CT_JSON = b"application/json"
_CT_TEXT = b"text/plain; charset=utf-8"
_CT_OCTET = b"application/octet-stream"
_CT_PLAIN = b"text/plain"
_HEADER_CT = b"content-type"


class Faster:
    """The main FasterAPI application class, implementing the ASGI interface."""

    __slots__ = (
        "title", "version", "description",
        "openapi_url", "docs_url", "redoc_url",
        "routes", "startup_handlers", "shutdown_handlers",
        "middleware", "exception_handlers",
        "_router", "_openapi_cache", "_middleware_app", "_ws_routes",
    )

    def __init__(
        self,
        *,
        title: str = "FasterAPI",
        version: str = "0.1.1",
        description: str = "",
        openapi_url: str | None = "/openapi.json",
        docs_url: str | None = "/docs",
        redoc_url: str | None = "/redoc",
    ) -> None:
        self.title = title
        self.version = version
        self.description = description
        self.openapi_url = openapi_url
        self.docs_url = docs_url
        self.redoc_url = redoc_url
        self.routes: list[dict[str, Any]] = []
        self.startup_handlers: list[Callable] = []
        self.shutdown_handlers: list[Callable] = []
        self.middleware: list[dict[str, Any]] = []
        self.exception_handlers: dict[type, Callable] = {}
        self._router = RadixRouter()
        self._openapi_cache: dict[str, Any] | None = None
        self._middleware_app: Callable | None = None
        self._ws_routes: dict[str, Callable] = {}
        self._setup_openapi_routes()

    def __repr__(self) -> str:
        return f"<Faster routes={len(self.routes)}>"

    # ------------------------------------------------------------------
    #  OpenAPI auto-routes
    # ------------------------------------------------------------------

    def _setup_openapi_routes(self) -> None:
        if self.openapi_url is not None:
            api_url = self.openapi_url
            app_ref = self

            async def openapi_schema() -> JSONResponse:
                spec = generate_openapi(
                    app_ref, title=app_ref.title,
                    version=app_ref.version, description=app_ref.description,
                )
                return JSONResponse(spec)

            self._add_route(
                "GET", api_url, openapi_schema,
                tags=["openapi"], summary="OpenAPI Schema",
                response_model=None, status_code=200, deprecated=False,
            )

        if self.docs_url is not None and self.openapi_url is not None:
            ourl, t = self.openapi_url, self.title

            async def swagger_docs() -> HTMLResponse:
                return HTMLResponse(swagger_ui_html(ourl, title=f"{t} - Swagger UI"))

            self._add_route(
                "GET", self.docs_url, swagger_docs,
                tags=["openapi"], summary="Swagger UI",
                response_model=None, status_code=200, deprecated=False,
            )

        if self.redoc_url is not None and self.openapi_url is not None:
            ourl, t = self.openapi_url, self.title

            async def redoc_docs() -> HTMLResponse:
                return HTMLResponse(redoc_html(ourl, title=f"{t} - ReDoc"))

            self._add_route(
                "GET", self.redoc_url, redoc_docs,
                tags=["openapi"], summary="ReDoc",
                response_model=None, status_code=200, deprecated=False,
            )

    # ------------------------------------------------------------------
    #  ASGI interface
    # ------------------------------------------------------------------

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if self.middleware:
            if self._middleware_app is None:
                self._middleware_app = self._build_middleware_chain()
            await self._middleware_app(scope, receive, send)
        else:
            await self._asgi_app(scope, receive, send)

    async def _asgi_app(self, scope: dict, receive: Callable, send: Callable) -> None:
        scope_type = scope["type"]
        if scope_type == "http":
            await self._handle_http(scope, receive, send)
        elif scope_type == "websocket":
            await self._handle_websocket(scope, receive, send)
        elif scope_type == "lifespan":
            await self._handle_lifespan(scope, receive, send)

    def _build_middleware_chain(self) -> Callable:
        app = self._asgi_app
        for entry in reversed(self.middleware):
            app = entry["class"](app, **entry["kwargs"])
        return app

    # ------------------------------------------------------------------
    #  HTTP dispatch — hot path
    # ------------------------------------------------------------------

    async def _handle_http(self, scope: dict, receive: Callable, send: Callable) -> None:
        result = self._router.resolve(scope["method"], scope["path"])
        if result is None:
            await _send_error(send, 404, "Not Found")
            return

        handler, path_params, metadata = result
        scope["path_params"] = path_params
        request = Request(scope, receive)
        bg_tasks = None

        try:
            response, bg_tasks = await _resolve_handler(handler, request, path_params)
        except RequestValidationError as exc:
            status, body, headers = await self._handle_exc(
                request, exc, RequestValidationError,
                _default_validation_exception_handler,
            )
            await _send_raw(send, status, body, headers)
            return
        except HTTPException as exc:
            status, body, headers = await self._handle_exc(
                request, exc, HTTPException,
                _default_http_exception_handler,
            )
            await _send_raw(send, status, body, headers)
            return
        except Exception as exc:
            for exc_class in type(exc).__mro__:
                if exc_class in self.exception_handlers:
                    response = self.exception_handlers[exc_class](request, exc)
                    if asyncio.iscoroutine(response):
                        response = await response
                    break
            else:
                await _send_error(send, 500, "Internal Server Error")
                return

        await _send_response(send, metadata.get("status_code", 200), response)

        if bg_tasks is not None:
            await bg_tasks.run()

    async def _handle_exc(
        self, request: Request, exc: Exception, exc_class: type,
        default_handler: Callable,
    ) -> tuple[int, bytes, list[tuple[bytes, bytes]]]:
        handler = self.exception_handlers.get(exc_class, default_handler)
        result = handler(request, exc)
        if asyncio.iscoroutine(result):
            result = await result
        return result  # type: ignore[return-value]

    # ------------------------------------------------------------------
    #  WebSocket dispatch
    # ------------------------------------------------------------------

    async def _handle_websocket(
        self, scope: dict, receive: Callable, send: Callable,
    ) -> None:
        path = scope.get("path", "/")
        handler = self._ws_routes.get(path.rstrip("/") or "/")
        if handler is None:
            await send({"type": "websocket.close", "code": 4004})
            return
        ws = WebSocket(scope, receive, send)
        await handler(ws)

    # ------------------------------------------------------------------
    #  Lifespan
    # ------------------------------------------------------------------

    async def _handle_lifespan(
        self, scope: dict, receive: Callable, send: Callable,
    ) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    for h in self.startup_handlers:
                        r = h()
                        if asyncio.iscoroutine(r):
                            await r
                    await send({"type": "lifespan.startup.complete"})
                except Exception as exc:
                    await send({"type": "lifespan.startup.failed", "message": str(exc)})
                    return
            elif message["type"] == "lifespan.shutdown":
                try:
                    for h in self.shutdown_handlers:
                        r = h()
                        if asyncio.iscoroutine(r):
                            await r
                    await send({"type": "lifespan.shutdown.complete"})
                except Exception:
                    pass
                return

    # ------------------------------------------------------------------
    #  Route registration
    # ------------------------------------------------------------------

    def _add_route(
        self, method: str, path: str, handler: Callable, *,
        tags: list[str], summary: str, response_model: Any,
        status_code: int, deprecated: bool,
    ) -> None:
        metadata = {
            "tags": tags, "summary": summary,
            "response_model": response_model,
            "status_code": status_code, "deprecated": deprecated,
        }
        self.routes.append({"method": method, "path": path, "handler": handler, **metadata})
        self._router.add_route(method, path, handler, metadata)
        compile_handler(handler)  # pre-compile at registration time

    def _route_decorator(self, method: str, path: str, **kw: Any) -> Callable:
        def decorator(handler: Callable) -> Callable:
            self._add_route(
                method, path, handler,
                tags=kw.get("tags") or [],
                summary=kw.get("summary", ""),
                response_model=kw.get("response_model"),
                status_code=kw.get("status_code", 200),
                deprecated=kw.get("deprecated", False),
            )
            return handler
        return decorator

    def get(self, path: str, **kw: Any) -> Callable:
        return self._route_decorator("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> Callable:
        return self._route_decorator("POST", path, **kw)

    def put(self, path: str, **kw: Any) -> Callable:
        return self._route_decorator("PUT", path, **kw)

    def delete(self, path: str, **kw: Any) -> Callable:
        return self._route_decorator("DELETE", path, **kw)

    def patch(self, path: str, **kw: Any) -> Callable:
        return self._route_decorator("PATCH", path, **kw)

    def websocket(self, path: str) -> Callable:
        def decorator(handler: Callable) -> Callable:
            self._ws_routes[path.rstrip("/") or "/"] = handler
            return handler
        return decorator

    # ------------------------------------------------------------------
    #  Lifecycle hooks
    # ------------------------------------------------------------------

    def on_startup(self, handler: Callable) -> Callable:
        self.startup_handlers.append(handler)
        return handler

    def on_shutdown(self, handler: Callable) -> Callable:
        self.shutdown_handlers.append(handler)
        return handler

    # ------------------------------------------------------------------
    #  Middleware & exception handlers
    # ------------------------------------------------------------------

    def add_middleware(self, middleware_class: type, **kwargs: Any) -> None:
        self.middleware.append({"class": middleware_class, "kwargs": kwargs})
        self._middleware_app = None  # invalidate cached chain

    def add_exception_handler(self, exc_class: type, handler: Callable) -> None:
        self.exception_handlers[exc_class] = handler

    # ------------------------------------------------------------------
    #  Router inclusion
    # ------------------------------------------------------------------

    def include_router(
        self, router: Any, *, prefix: str = "", tags: Sequence[str] = (),
    ) -> None:
        pfx = prefix.rstrip("/")
        for route in router.routes:
            merged = dict(route)
            merged["path"] = pfx + merged["path"]
            merged["tags"] = list(tags) + merged["tags"]
            self.routes.append(merged)
            metadata = {k: v for k, v in merged.items() if k not in ("method", "path", "handler")}
            self._router.add_route(merged["method"], merged["path"], merged["handler"], metadata)
            compile_handler(merged["handler"])


# ------------------------------------------------------------------
#  Module-level send helpers (avoid method lookup on self)
# ------------------------------------------------------------------

async def _send_response(send: Callable, status_code: int, body: Any) -> None:
    if hasattr(body, "to_asgi"):
        await body.to_asgi(send)
        return
    if isinstance(body, bytes):
        ct = _CT_OCTET
    elif isinstance(body, str):
        body = body.encode()
        ct = _CT_TEXT
    elif body is None:
        body = b""
        ct = _CT_PLAIN
    else:
        body = msgspec.json.encode(body)
        ct = _CT_JSON
    await send({"type": "http.response.start", "status": status_code, "headers": [(_HEADER_CT, ct)]})
    await send({"type": "http.response.body", "body": body})


async def _send_raw(
    send: Callable, status: int, body: bytes, headers: list[tuple[bytes, bytes]],
) -> None:
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _send_error(send: Callable, status: int, message: str) -> None:
    body = msgspec.json.encode({"detail": message})
    await send({"type": "http.response.start", "status": status, "headers": [(_HEADER_CT, _CT_JSON)]})
    await send({"type": "http.response.body", "body": body})
