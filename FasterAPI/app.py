from __future__ import annotations

import asyncio
from typing import Any, Callable, Sequence

import uvloop

uvloop.install()


class Faster:
    def __init__(self) -> None:
        self.routes: list[dict[str, Any]] = []
        self.startup_handlers: list[Callable] = []
        self.shutdown_handlers: list[Callable] = []
        self.middleware: list[dict[str, Any]] = []
        self.exception_handlers: dict[type, Callable] = {}

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
        # Routing logic will be implemented later
        await send({
            "type": "http.response.start",
            "status": 404,
            "headers": [(b"content-type", b"text/plain")],
        })
        await send({
            "type": "http.response.body",
            "body": b"Not Found",
        })

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
        self.routes.append({
            "method": method,
            "path": path,
            "handler": handler,
            "tags": tags,
            "summary": summary,
            "response_model": response_model,
            "status_code": status_code,
            "deprecated": deprecated,
        })

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
        pass
