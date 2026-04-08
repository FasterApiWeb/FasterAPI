from __future__ import annotations

from typing import Any, Callable


class RadixNode:
    """A single node in the radix tree used for URL routing."""

    __slots__ = ("children", "handlers", "param_name", "is_param", "is_wildcard")

    def __init__(self) -> None:
        self.children: dict[str, RadixNode] = {}
        self.handlers: dict[str, tuple[Callable, dict[str, Any]]] = {}
        self.param_name: str | None = None
        self.is_param: bool = False
        self.is_wildcard: bool = False


class RadixRouter:
    """High-performance URL router using a radix tree for route matching."""

    def __init__(self) -> None:
        self.root = RadixNode()

    def add_route(
        self,
        method: str,
        path: str,
        handler: Callable,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a route handler for the given HTTP method and path pattern."""
        path = path.rstrip("/") or "/"
        segments = self._split(path)
        node = self.root

        for segment in segments:
            if segment.startswith("{") and segment.endswith("}"):
                param_name = segment[1:-1]
                if "*" not in node.children:
                    child = RadixNode()
                    child.is_param = True
                    child.param_name = param_name
                    node.children["*"] = child
                node = node.children["*"]
            else:
                if segment not in node.children:
                    node.children[segment] = RadixNode()
                node = node.children[segment]

        node.handlers[method.upper()] = (handler, metadata or {})

    def resolve(
        self, method: str, path: str
    ) -> tuple[Callable, dict[str, str], dict[str, Any]] | None:
        """Resolve a path to its handler, extracted path params, and metadata."""
        path = path.rstrip("/") or "/"
        segments = self._split(path)
        params: dict[str, str] = {}

        result = self._search(self.root, segments, 0, params)
        if result is None:
            return None

        node = result
        entry = node.handlers.get(method.upper())
        if entry is None:
            return None

        handler, metadata = entry
        return handler, params, metadata

    def _search(
        self,
        node: RadixNode,
        segments: list[str],
        index: int,
        params: dict[str, str],
    ) -> RadixNode | None:
        if index == len(segments):
            if node.handlers:
                return node
            return None

        segment = segments[index]

        # Try exact static match first
        if segment in node.children:
            result = self._search(node.children[segment], segments, index + 1, params)
            if result is not None:
                return result

        # Try param match
        if "*" in node.children:
            param_node = node.children["*"]
            name = param_node.param_name
            assert name is not None
            params[name] = segment
            result = self._search(param_node, segments, index + 1, params)
            if result is not None:
                return result
            del params[name]

        return None

    @staticmethod
    def _split(path: str) -> list[str]:
        return [s for s in path.split("/") if s]


class FasterRouter:
    """API router for grouping routes with a common prefix and tags."""

    def __init__(self, prefix: str = "", tags: list[str] | None = None) -> None:
        self.prefix = prefix.rstrip("/")
        self.tags: list[str] = tags or []
        self.routes: list[dict[str, Any]] = []

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
        full_path = self.prefix + path
        self.routes.append({
            "method": method,
            "path": full_path,
            "handler": handler,
            "tags": self.tags + tags,
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
        """Add a GET route to the router."""
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
        """Add a POST route to the router."""
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
        """Add a PUT route to the router."""
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
        """Add a DELETE route to the router."""
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
        """Add a PATCH route to the router."""
        def decorator(handler: Callable) -> Callable:
            self._add_route(
                "PATCH", path, handler,
                tags=tags or [], summary=summary,
                response_model=response_model, status_code=status_code,
                deprecated=deprecated,
            )
            return handler
        return decorator
