from __future__ import annotations

import asyncio
from typing import Any, Callable, Sequence

import msgspec.json
import uvloop

from .dependencies import _resolve_handler
from .exceptions import HTTPException
from .request import Request
from .router import RadixRouter

uvloop.install()


class Faster:
    def __init__(self) -> None:
        self.routes: list[dict[str, Any]] = []
        self.startup_handlers: list[Callable] = []
        self.shutdown_handlers: list[Callable] = []
        self.middleware: list[dict[str, Any]] = []
        self.exception_handlers: dict[type, Callable] = {}
        self._router = RadixRouter()

    def __repr__(self) -> str:
        return f"<Faster routes={len(self.routes)}>"

    # --- ASGI interface ---

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        scope_type = scope["type"]

        if scope_type == "lifespan":
            await self._handle_lifespan(scope, receive, send)
        elif scope_type == "http":
            await self._handle_http(scope, receive, send)
        else:
            raise RuntimeError(f"Unsupported scope type: {scope_type}")

    async def _handle_lifespan(self, scope: dict, receive: Callable, send: Callable) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    for handler in self.startup_handlers:
                        result = handler()
                        if asyncio.iscoroutine(result):
                            await result
                    await send({"type": "lifespan.startup.complete"})
                except Exception as exc:
                    await send({"type": "lifespan.startup.failed", "message": str(exc)})
                    return
            elif message["type"] == "lifespan.shutdown":
                try:
                    for handler in self.shutdown_handlers:
                        result = handler()
                        if asyncio.iscoroutine(result):
                            await result
                    await send({"type": "lifespan.shutdown.complete"})
                except Exception as exc:
                    await send({"type": "lifespan.shutdown.failed", "message": str(exc)})
                return

    async def _handle_http(self, scope: dict, receive: Callable, send: Callable) -> None:
        method = scope["method"]
        path = scope["path"]

        result = self._router.resolve(method, path)
        if result is None:
            await self._send_error(send, 404, "Not Found")
            return

        handler, path_params, metadata = result
        scope["path_params"] = path_params

        request = Request(scope, receive)
        try:
            response = await _resolve_handler(handler, request, path_params)
        except HTTPException as exc:
            body = msgspec.json.encode({"detail": exc.detail})
            headers = [(b"content-type", b"application/json")]
            if exc.headers:
                headers.extend(
                    (k.encode(), v.encode()) for k, v in exc.headers.items()
                )
            await send({
                "type": "http.response.start",
                "status": exc.status_code,
                "headers": headers,
            })
            await send({"type": "http.response.body", "body": body})
            return
        except Exception as exc:
            for exc_class in type(exc).__mro__:
                if exc_class in self.exception_handlers:
                    response = self.exception_handlers[exc_class](request, exc)
                    if asyncio.iscoroutine(response):
                        response = await response
                    break
            else:
                await self._send_error(send, 500, "Internal Server Error")
                return

        status_code = metadata.get("status_code", 200)
        await self._send_response(send, status_code, response)

    async def _send_response(
        self, send: Callable, status_code: int, body: Any,
    ) -> None:
        if isinstance(body, bytes):
            content = body
            ct = b"application/octet-stream"
        elif isinstance(body, str):
            content = body.encode()
            ct = b"text/plain; charset=utf-8"
        elif body is None:
            content = b""
            ct = b"text/plain"
        else:
            content = msgspec.json.encode(body)
            ct = b"application/json"
        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": [(b"content-type", ct)],
        })
        await send({"type": "http.response.body", "body": content})

    @staticmethod
    async def _send_error(send: Callable, status: int, message: str) -> None:
        body = msgspec.json.encode({"detail": message})
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({"type": "http.response.body", "body": body})

    # --- Route decorators ---

    def _add_route(
        self,
        method: str,
        path: str,
        handler: Callable,
        *,
        tags: list[str],
        summary: str,
        response_model: Any,
        status_code: int,
        deprecated: bool,
    ) -> None:
        metadata = {
            "tags": tags,
            "summary": summary,
            "response_model": response_model,
            "status_code": status_code,
            "deprecated": deprecated,
        }
        self.routes.append({
            "method": method,
            "path": path,
            "handler": handler,
            **metadata,
        })
        self._router.add_route(method, path, handler, metadata)

    def get(
        self,
        path: str,
        *,
        tags: list[str] | None = None,
        summary: str = "",
        response_model: Any = None,
        status_code: int = 200,
        deprecated: bool = False,
    ) -> Callable:
        def decorator(handler: Callable) -> Callable:
            self._add_route(
                "GET", path, handler,
                tags=tags or [], summary=summary,
                response_model=response_model, status_code=status_code,
                deprecated=deprecated,
            )
            return handler
        return decorator

    def post(
        self,
        path: str,
        *,
        tags: list[str] | None = None,
        summary: str = "",
        response_model: Any = None,
        status_code: int = 200,
        deprecated: bool = False,
    ) -> Callable:
        def decorator(handler: Callable) -> Callable:
            self._add_route(
                "POST", path, handler,
                tags=tags or [], summary=summary,
                response_model=response_model, status_code=status_code,
                deprecated=deprecated,
            )
            return handler
        return decorator

    def put(
        self,
        path: str,
        *,
        tags: list[str] | None = None,
        summary: str = "",
        response_model: Any = None,
        status_code: int = 200,
        deprecated: bool = False,
    ) -> Callable:
        def decorator(handler: Callable) -> Callable:
            self._add_route(
                "PUT", path, handler,
                tags=tags or [], summary=summary,
                response_model=response_model, status_code=status_code,
                deprecated=deprecated,
            )
            return handler
        return decorator

    def delete(
        self,
        path: str,
        *,
        tags: list[str] | None = None,
        summary: str = "",
        response_model: Any = None,
        status_code: int = 200,
        deprecated: bool = False,
    ) -> Callable:
        def decorator(handler: Callable) -> Callable:
            self._add_route(
                "DELETE", path, handler,
                tags=tags or [], summary=summary,
                response_model=response_model, status_code=status_code,
                deprecated=deprecated,
            )
            return handler
        return decorator

    def patch(
        self,
        path: str,
        *,
        tags: list[str] | None = None,
        summary: str = "",
        response_model: Any = None,
        status_code: int = 200,
        deprecated: bool = False,
    ) -> Callable:
        def decorator(handler: Callable) -> Callable:
            self._add_route(
                "PATCH", path, handler,
                tags=tags or [], summary=summary,
                response_model=response_model, status_code=status_code,
                deprecated=deprecated,
            )
            return handler
        return decorator

    # --- Lifecycle hooks ---

    def on_startup(self, handler: Callable) -> Callable:
        self.startup_handlers.append(handler)
        return handler

    def on_shutdown(self, handler: Callable) -> Callable:
        self.shutdown_handlers.append(handler)
        return handler

    # --- Middleware ---

    def add_middleware(self, middleware_class: type, **kwargs: Any) -> None:
        self.middleware.append({"class": middleware_class, "kwargs": kwargs})

    # --- Exception handlers ---

    def add_exception_handler(self, exc_class: type, handler: Callable) -> None:
        self.exception_handlers[exc_class] = handler

    # --- Router inclusion ---

    def include_router(
        self,
        router: Any,
        *,
        prefix: str = "",
        tags: Sequence[str] = (),
    ) -> None:
        prefix = prefix.rstrip("/")
        for route in router.routes:
            merged = dict(route)
            merged["path"] = prefix + merged["path"]
            merged["tags"] = list(tags) + merged["tags"]
            self.routes.append(merged)
            metadata = {
                k: v for k, v in merged.items()
                if k not in ("method", "path", "handler")
            }
            self._router.add_route(
                merged["method"], merged["path"], merged["handler"], metadata,
            )
