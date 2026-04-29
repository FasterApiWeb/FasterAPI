"""Core Faster application class — the ASGI entry point.

Optimisations over a naïve implementation:
  - Handler signatures are compiled once at route registration
  - Middleware chain is built once and cached
  - JSON responses use msgspec.json.encode (Rust-backed, zero-copy)
  - Common response path (dict → JSON bytes) avoids Response object overhead
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from collections.abc import Callable, Sequence
from typing import Any, cast

from ._version import get_version
from .concurrency import install_event_loop
from .dependencies import Depends, _resolve_handler, compile_handler
from .exceptions import (
    HTTPException,
    RequestValidationError,
    _default_http_exception_handler,
    _default_validation_exception_handler,
)
from .openapi.generator import generate_openapi
from .openapi.ui import redoc_html, swagger_ui_html
from .request import Request
from .response import HTMLResponse, JSONResponse, encode_json
from .router import RadixRouter
from .types import ASGIApp
from .websocket import WebSocket

__all__ = ["Faster"]

_event_loop = install_event_loop()

_CT_JSON = b"application/json"
_CT_TEXT = b"text/plain; charset=utf-8"
_CT_OCTET = b"application/octet-stream"
_CT_PLAIN = b"text/plain"
_HEADER_CT = b"content-type"


class Faster:
    """The main FasterAPI application class, implementing the ASGI interface."""

    __slots__ = (
        "title",
        "version",
        "description",
        "openapi_url",
        "docs_url",
        "redoc_url",
        "openapi_tags",
        "terms_of_service",
        "contact",
        "license_info",
        "routes",
        "startup_handlers",
        "shutdown_handlers",
        "lifespan",
        "middleware",
        "exception_handlers",
        "_router",
        "_openapi_cache",
        "_middleware_app",
        "_ws_routes",
        "_mounts",
        "max_body_size",
        "stream_request_body",
        "stream_multipart",
    )

    def __init__(
        self,
        *,
        title: str = "FasterAPI",
        version: str | None = None,
        description: str = "",
        openapi_url: str | None = "/openapi.json",
        docs_url: str | None = "/docs",
        redoc_url: str | None = "/redoc",
        openapi_tags: list[dict[str, Any]] | None = None,
        terms_of_service: str | None = None,
        contact: dict[str, str] | None = None,
        license_info: dict[str, str] | None = None,
        lifespan: Callable[[Faster], Any] | None = None,
        max_body_size: int | None = None,
        stream_request_body: bool = False,
        stream_multipart: bool = False,
    ) -> None:
        self.title = title
        self.version = version if version is not None else get_version()
        self.description = description
        self.openapi_url = openapi_url
        self.docs_url = docs_url
        self.redoc_url = redoc_url
        self.openapi_tags = openapi_tags
        self.terms_of_service = terms_of_service
        self.contact = contact
        self.license_info = license_info
        self.lifespan = lifespan
        self.routes: list[dict[str, Any]] = []
        self.startup_handlers: list[Callable[[], Any]] = []
        self.shutdown_handlers: list[Callable[[], Any]] = []
        self.middleware: list[dict[str, Any]] = []
        self.exception_handlers: dict[type, Any] = {}
        self._router = RadixRouter()
        self._openapi_cache: dict[str, Any] | None = None
        self._middleware_app: ASGIApp | None = None
        self._ws_routes: dict[str, ASGIApp] = {}
        self._mounts: list[tuple[str, ASGIApp]] = []
        self.max_body_size = max_body_size
        self.stream_request_body = stream_request_body
        self.stream_multipart = stream_multipart
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
                    app_ref,
                    title=app_ref.title,
                    version=app_ref.version,
                    description=app_ref.description,
                    openapi_tags=app_ref.openapi_tags,
                    terms_of_service=app_ref.terms_of_service,
                    contact=app_ref.contact,
                    license_info=app_ref.license_info,
                )
                return JSONResponse(spec)

            self._add_route(
                "GET",
                api_url,
                openapi_schema,
                tags=["openapi"],
                summary="OpenAPI Schema",
                response_model=None,
                status_code=200,
                deprecated=False,
                responses=None,
                dependencies=None,
            )

        if self.docs_url is not None and self.openapi_url is not None:
            ourl, t = self.openapi_url, self.title

            async def swagger_docs() -> HTMLResponse:
                return HTMLResponse(swagger_ui_html(ourl, title=f"{t} - Swagger UI"))

            self._add_route(
                "GET",
                self.docs_url,
                swagger_docs,
                tags=["openapi"],
                summary="Swagger UI",
                response_model=None,
                status_code=200,
                deprecated=False,
                responses=None,
                dependencies=None,
            )

        if self.redoc_url is not None and self.openapi_url is not None:
            ourl, t = self.openapi_url, self.title

            async def redoc_docs() -> HTMLResponse:
                return HTMLResponse(redoc_html(ourl, title=f"{t} - ReDoc"))

            self._add_route(
                "GET",
                self.redoc_url,
                redoc_docs,
                tags=["openapi"],
                summary="ReDoc",
                response_model=None,
                status_code=200,
                deprecated=False,
                responses=None,
                dependencies=None,
            )

    # ------------------------------------------------------------------
    #  ASGI interface
    # ------------------------------------------------------------------

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        if self.middleware:
            if self._middleware_app is None:
                self._middleware_app = self._build_middleware_chain()
            await self._middleware_app(scope, receive, send)
        else:
            await self._asgi_app(scope, receive, send)

    async def _asgi_app(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        scope_type = scope["type"]
        if scope_type == "http":
            # Check mounts first
            path: str = scope.get("path", "/")
            for prefix, mounted_app in self._mounts:
                if path == prefix or path.startswith(prefix + "/"):
                    sub_scope = dict(scope)
                    sub_scope["path"] = path[len(prefix) :] or "/"
                    sub_scope["root_path"] = scope.get("root_path", "") + prefix
                    await mounted_app(sub_scope, receive, send)
                    return
            await self._handle_http(scope, receive, send)
        elif scope_type == "websocket":
            await self._handle_websocket(scope, receive, send)
        elif scope_type == "lifespan":
            await self._handle_lifespan(scope, receive, send)

    def _build_middleware_chain(self) -> ASGIApp:
        app = self._asgi_app
        for entry in reversed(self.middleware):
            app = entry["class"](app, **entry["kwargs"])
        return app

    # ------------------------------------------------------------------
    #  HTTP dispatch — hot path
    # ------------------------------------------------------------------

    async def _handle_http(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        result = self._router.resolve(scope["method"], scope["path"])
        if result is None:
            await _send_error(send, 404, "Not Found")
            return

        handler, path_params, metadata = result
        scope["path_params"] = path_params
        st = scope.setdefault("state", {})
        st["max_body_size"] = self.max_body_size
        st["stream_body_no_buffer"] = self.stream_request_body
        st["stream_multipart"] = self.stream_multipart
        request = Request(scope, receive)
        bg_tasks = None

        extra_deps: list[Depends] | None = metadata.get("dependencies")

        try:
            response, bg_tasks = await _resolve_handler(handler, request, path_params, extra_deps)
        except RequestValidationError as exc:
            status, body, headers = await self._handle_exc(
                request,
                exc,
                RequestValidationError,
                _default_validation_exception_handler,
            )
            await _send_raw(send, status, body, headers)
            return
        except HTTPException as exc:
            status, body, headers = await self._handle_exc(
                request,
                exc,
                HTTPException,
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

        # Apply response_model filtering if configured
        response_model = metadata.get("response_model")
        response_model_include = metadata.get("response_model_include")
        response_model_exclude = metadata.get("response_model_exclude")
        if response_model is not None and not hasattr(response, "to_asgi"):
            response = _apply_response_model(response, response_model, response_model_include, response_model_exclude)

        await _send_response(send, metadata.get("status_code", 200), response)

        if bg_tasks is not None:
            await bg_tasks.run()

    async def _handle_exc(
        self,
        request: Request,
        exc: Exception,
        exc_class: type,
        default_handler: Any,
    ) -> tuple[int, bytes, list[tuple[bytes, bytes]]]:
        handler = self.exception_handlers.get(exc_class, default_handler)
        result = handler(request, exc)
        if asyncio.iscoroutine(result):
            result = await result
        return cast(tuple[int, bytes, list[tuple[bytes, bytes]]], result)

    # ------------------------------------------------------------------
    #  WebSocket dispatch
    # ------------------------------------------------------------------

    async def _handle_websocket(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
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
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        if self.lifespan is not None:
            await self._run_lifespan_context(receive, send)
            return

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

    async def _run_lifespan_context(self, receive: Any, send: Any) -> None:
        """Run the lifespan async context manager."""
        assert self.lifespan is not None
        ctx = self.lifespan(self)
        # Support both @asynccontextmanager functions and plain async generators
        if hasattr(ctx, "__aenter__"):
            async with ctx:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                message = await receive()
                if message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
        else:
            # Treat as async generator
            gen = ctx.__aiter__() if hasattr(ctx, "__aiter__") else ctx
            with contextlib.suppress(StopAsyncIteration):
                await gen.__anext__()
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            message = await receive()
            if message["type"] == "lifespan.shutdown":
                with contextlib.suppress(StopAsyncIteration):
                    await gen.__anext__()
                await send({"type": "lifespan.shutdown.complete"})

    # ------------------------------------------------------------------
    #  Route registration
    # ------------------------------------------------------------------

    def _add_route(
        self,
        method: str,
        path: str,
        handler: ASGIApp,
        *,
        tags: list[str],
        summary: str,
        response_model: Any,
        status_code: int,
        deprecated: bool,
        responses: dict[int | str, dict[str, Any]] | None,
        dependencies: list[Depends] | None,
        response_model_include: set[str] | None = None,
        response_model_exclude: set[str] | None = None,
        openapi_extra: dict[str, Any] | None = None,
    ) -> None:
        metadata: dict[str, Any] = {
            "tags": tags,
            "summary": summary,
            "response_model": response_model,
            "response_model_include": response_model_include,
            "response_model_exclude": response_model_exclude,
            "status_code": status_code,
            "deprecated": deprecated,
            "responses": responses,
            "dependencies": dependencies,
            "openapi_extra": openapi_extra,
        }
        self.routes.append({"method": method, "path": path, "handler": handler, **metadata})
        self._router.add_route(method, path, handler, metadata)
        compile_handler(handler)

    def _route_decorator(self, method: str, path: str, **kw: Any) -> Callable[[ASGIApp], ASGIApp]:
        def decorator(handler: ASGIApp) -> ASGIApp:
            self._add_route(
                method,
                path,
                handler,
                tags=kw.get("tags") or [],
                summary=kw.get("summary", ""),
                response_model=kw.get("response_model"),
                response_model_include=kw.get("response_model_include"),
                response_model_exclude=kw.get("response_model_exclude"),
                status_code=kw.get("status_code", 200),
                deprecated=kw.get("deprecated", False),
                responses=kw.get("responses"),
                dependencies=kw.get("dependencies"),
                openapi_extra=kw.get("openapi_extra"),
            )
            return handler

        return decorator

    def get(self, path: str, **kw: Any) -> Callable[[ASGIApp], ASGIApp]:
        return self._route_decorator("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> Callable[[ASGIApp], ASGIApp]:
        return self._route_decorator("POST", path, **kw)

    def put(self, path: str, **kw: Any) -> Callable[[ASGIApp], ASGIApp]:
        return self._route_decorator("PUT", path, **kw)

    def delete(self, path: str, **kw: Any) -> Callable[[ASGIApp], ASGIApp]:
        return self._route_decorator("DELETE", path, **kw)

    def patch(self, path: str, **kw: Any) -> Callable[[ASGIApp], ASGIApp]:
        return self._route_decorator("PATCH", path, **kw)

    def websocket(self, path: str) -> Callable[[ASGIApp], ASGIApp]:
        def decorator(handler: ASGIApp) -> ASGIApp:
            self._ws_routes[path.rstrip("/") or "/"] = handler
            return handler

        return decorator

    # ------------------------------------------------------------------
    #  Sub-application mounting
    # ------------------------------------------------------------------

    def mount(self, path: str, app: ASGIApp, name: str | None = None) -> None:
        """Mount an ASGI sub-application (e.g. StaticFiles) at *path*.

        Example::

            app.mount("/static", StaticFiles(directory="static"), name="static")
        """
        prefix = path.rstrip("/")
        self._mounts.append((prefix, app))

    # ------------------------------------------------------------------
    #  Lifecycle hooks
    # ------------------------------------------------------------------

    def on_startup(self, handler: Callable[[], Any]) -> Callable[[], Any]:
        self.startup_handlers.append(handler)
        return handler

    def on_shutdown(self, handler: Callable[[], Any]) -> Callable[[], Any]:
        self.shutdown_handlers.append(handler)
        return handler

    # ------------------------------------------------------------------
    #  Middleware & exception handlers
    # ------------------------------------------------------------------

    def add_middleware(self, middleware_class: type, **kwargs: Any) -> None:
        self.middleware.append({"class": middleware_class, "kwargs": kwargs})
        self._middleware_app = None  # invalidate cached chain

    def add_exception_handler(self, exc_class: type, handler: Any) -> None:
        self.exception_handlers[exc_class] = handler

    # ------------------------------------------------------------------
    #  Router inclusion
    # ------------------------------------------------------------------

    def include_router(
        self,
        router: Any,
        *,
        prefix: str = "",
        tags: Sequence[str] = (),
        dependencies: list[Depends] | None = None,
    ) -> None:
        pfx = prefix.rstrip("/")
        for route in router.routes:
            merged = dict(route)
            merged["path"] = pfx + merged["path"]
            merged["tags"] = list(tags) + merged["tags"]
            # Merge router-level dependencies with route-level dependencies
            route_deps: list[Depends] = merged.get("dependencies") or []
            router_deps: list[Depends] = getattr(router, "dependencies", None) or []
            caller_deps: list[Depends] = dependencies or []
            merged_deps = caller_deps + router_deps + route_deps
            merged["dependencies"] = merged_deps if merged_deps else None
            self.routes.append(merged)
            metadata = {k: v for k, v in merged.items() if k not in ("method", "path", "handler")}
            self._router.add_route(merged["method"], merged["path"], merged["handler"], metadata)
            compile_handler(merged["handler"])


# ------------------------------------------------------------------
#  Response model filtering
# ------------------------------------------------------------------


def _apply_response_model(
    result: Any,
    model: type,
    include: set[str] | None,
    exclude: set[str] | None,
) -> Any:
    """Filter *result* to only the fields defined in *model*."""
    import msgspec.structs

    if isinstance(result, msgspec.Struct):
        data = {f.name: getattr(result, f.name) for f in msgspec.structs.fields(result)}
    elif dataclasses.is_dataclass(result) and not isinstance(result, type):
        data = dataclasses.asdict(result)
    elif isinstance(result, dict):
        data = result
    else:
        return result

    # Determine allowed field names from the response model
    try:
        if issubclass(model, msgspec.Struct):
            allowed: set[str] = {f.name for f in msgspec.structs.fields(model)}
        elif dataclasses.is_dataclass(model):
            allowed = {f.name for f in dataclasses.fields(model)}
        else:
            allowed = set(data.keys())
    except TypeError:
        allowed = set(data.keys())

    if include is not None:
        allowed &= include
    if exclude is not None:
        allowed -= exclude

    return {k: v for k, v in data.items() if k in allowed}


# ------------------------------------------------------------------
#  Module-level send helpers (avoid method lookup on self)
# ------------------------------------------------------------------


async def _send_response(send: Any, status_code: int, body: Any) -> None:
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
        body = encode_json(body)
        ct = _CT_JSON
    await send({"type": "http.response.start", "status": status_code, "headers": [(_HEADER_CT, ct)]})
    await send({"type": "http.response.body", "body": body})


async def _send_raw(
    send: Any,
    status: int,
    body: bytes,
    headers: list[tuple[bytes, bytes]],
) -> None:
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _send_error(send: Any, status: int, message: str) -> None:
    body = encode_json({"detail": message})
    await send({"type": "http.response.start", "status": status, "headers": [(_HEADER_CT, _CT_JSON)]})
    await send({"type": "http.response.body", "body": body})
