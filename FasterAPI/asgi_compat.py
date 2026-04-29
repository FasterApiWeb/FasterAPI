"""ASGI server interoperability helpers (HTTP/2, Hypercorn, Daphne, Uvicorn).

HTTP/2 terminates at the ASGI server; applications receive HTTP-style scopes.
These helpers avoid assumptions that break across servers or HTTP versions.
"""

from __future__ import annotations

from typing import Any


def http_version(scope: dict[str, Any]) -> str:
    """Return HTTP version string from scope (e.g. ``\"1.1\"``, ``\"2\"``)."""
    ver = scope.get("http_version")
    if isinstance(ver, str):
        return ver
    return "1.1"


def is_http2(scope: dict[str, Any]) -> bool:
    """True when the ASGI server reports HTTP/2 for this connection."""
    return http_version(scope).startswith("2")


def get_header(scope: dict[str, Any], name: str) -> str | None:
    """Case-insensitive header lookup from ASGI ``scope[\"headers\"]``."""
    want = name.lower().encode("latin-1")
    for k, v in scope.get("headers", []):
        if k.lower() == want:
            return v.decode("latin-1")
    return None


def get_server_host(scope: dict[str, Any]) -> str | None:
    """Hostname for virtual hosting: ``Host`` or ``:authority``, then ``server`` tuple."""
    for k, v in scope.get("headers", []):
        lk = k.lower()
        if lk in (b"host", b":authority"):
            return v.decode("latin-1").split(":")[0]
    server = scope.get("server")
    if isinstance(server, tuple | list) and len(server) >= 1:
        return str(server[0])
    return None
