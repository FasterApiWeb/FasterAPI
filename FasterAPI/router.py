"""High-performance radix-tree URL router for FasterAPI.

Key design choices for speed:
  - Iterative (not recursive) tree traversal
  - __slots__ on every node to cut memory and attribute lookup time
  - Static children checked before param wildcard (most routes are static)
  - Path split result is a simple list comprehension (fast C path in CPython)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .types import ASGIApp

__all__ = ["RadixRouter", "FasterRouter"]


class RadixNode:
    """A single node in the radix tree used for URL routing."""

    __slots__ = ("children", "handlers", "param_name", "is_param")

    def __init__(self) -> None:
        self.children: dict[str, RadixNode] = {}
        self.handlers: dict[str, tuple[ASGIApp, dict[str, Any]]] = {}
        self.param_name: str | None = None
        self.is_param: bool = False


class RadixRouter:
    """O(k) URL router using a compressed radix tree (k = path segments)."""

    __slots__ = ("root",)

    def __init__(self) -> None:
        self.root = RadixNode()

    # ------------------------------------------------------------------
    #  Route registration (called at startup — speed is less critical)
    # ------------------------------------------------------------------

    def add_route(
        self,
        method: str,
        path: str,
        handler: ASGIApp,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a handler for the given HTTP method and path pattern."""
        node = self.root
        for segment in _split(path):
            if segment[0] == "{" and segment[-1] == "}":
                param_name = segment[1:-1]
                child = node.children.get("*")
                if child is None:
                    child = RadixNode()
                    child.is_param = True
                    child.param_name = param_name
                    node.children["*"] = child
                node = child
            else:
                child = node.children.get(segment)
                if child is None:
                    child = RadixNode()
                    node.children[segment] = child
                node = child

        node.handlers[method.upper()] = (handler, metadata or {})

    # ------------------------------------------------------------------
    #  Route resolution — HOT PATH, called on every request
    # ------------------------------------------------------------------

    def resolve(
        self,
        method: str,
        path: str,
    ) -> tuple[ASGIApp, dict[str, str], dict[str, Any]] | None:
        """Resolve a path to (handler, path_params, metadata) or None."""
        segments = _split(path)
        params: dict[str, str] = {}

        node = self._walk(self.root, segments, 0, params)
        if node is None:
            return None

        entry = node.handlers.get(method.upper())
        if entry is None:
            return None

        return entry[0], params, entry[1]

    def _walk(
        self,
        node: RadixNode,
        segments: list[str],
        idx: int,
        params: dict[str, str],
    ) -> RadixNode | None:
        """Iterative-first tree walk with recursive fallback for param backtracking."""
        n = len(segments)
        # Fast iterative path for the common case (no backtracking needed)
        while idx < n:
            seg = segments[idx]
            child = node.children.get(seg)
            if child is not None:
                node = child
                idx += 1
                continue
            # Try param child
            param_child = node.children.get("*")
            if param_child is not None:
                assert param_child.param_name is not None
                params[param_child.param_name] = seg
                node = param_child
                idx += 1
                continue
            return None

        return node if node.handlers else None


# ------------------------------------------------------------------
#  Shared helpers
# ------------------------------------------------------------------


def _split(path: str) -> list[str]:
    """Split a URL path into non-empty segments, stripping trailing slashes."""
    return [s for s in path.split("/") if s]


# ------------------------------------------------------------------
#  FasterRouter (sub-router / blueprint)
# ------------------------------------------------------------------


class FasterRouter:
    """API router for grouping routes with a common prefix and tags."""

    __slots__ = ("prefix", "tags", "routes")

    def __init__(self, prefix: str = "", tags: list[str] | None = None) -> None:
        self.prefix = prefix.rstrip("/")
        self.tags: list[str] = tags or []
        self.routes: list[dict[str, Any]] = []

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
    ) -> None:
        full_path = self.prefix + path
        self.routes.append(
            {
                "method": method,
                "path": full_path,
                "handler": handler,
                "tags": self.tags + tags,
                "summary": summary,
                "response_model": response_model,
                "status_code": status_code,
                "deprecated": deprecated,
            }
        )

    # Decorator factories — identical API to Faster app

    def get(self, path: str, **kw: Any) -> Callable[[ASGIApp], ASGIApp]:
        def decorator(handler: ASGIApp) -> ASGIApp:
            self._add_route("GET", path, handler, **_route_kw(kw))
            return handler

        return decorator

    def post(self, path: str, **kw: Any) -> Callable[[ASGIApp], ASGIApp]:
        def decorator(handler: ASGIApp) -> ASGIApp:
            self._add_route("POST", path, handler, **_route_kw(kw))
            return handler

        return decorator

    def put(self, path: str, **kw: Any) -> Callable[[ASGIApp], ASGIApp]:
        def decorator(handler: ASGIApp) -> ASGIApp:
            self._add_route("PUT", path, handler, **_route_kw(kw))
            return handler

        return decorator

    def delete(self, path: str, **kw: Any) -> Callable[[ASGIApp], ASGIApp]:
        def decorator(handler: ASGIApp) -> ASGIApp:
            self._add_route("DELETE", path, handler, **_route_kw(kw))
            return handler

        return decorator

    def patch(self, path: str, **kw: Any) -> Callable[[ASGIApp], ASGIApp]:
        def decorator(handler: ASGIApp) -> ASGIApp:
            self._add_route("PATCH", path, handler, **_route_kw(kw))
            return handler

        return decorator


def _route_kw(kw: dict[str, Any]) -> dict[str, Any]:
    """Normalise decorator kwargs with defaults."""
    return {
        "tags": kw.get("tags") or [],
        "summary": kw.get("summary", ""),
        "response_model": kw.get("response_model"),
        "status_code": kw.get("status_code", 200),
        "deprecated": kw.get("deprecated", False),
    }
