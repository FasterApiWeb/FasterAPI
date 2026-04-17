"""StaticFiles ASGI application for serving files from a directory."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

__all__ = ["StaticFiles"]

_CT_JSON = b"application/json"
_NOT_FOUND = b'{"detail":"Not Found"}'
_METHOD_NOT_ALLOWED = b'{"detail":"Method Not Allowed"}'


class StaticFiles:
    """Serve static files from a local directory as an ASGI application.

    Usage::

        app.mount("/static", StaticFiles(directory="static"), name="static")

    Requests to ``/static/logo.png`` will serve ``static/logo.png`` from disk.
    Set ``html=True`` to serve ``index.html`` for directory requests.
    """

    def __init__(self, *, directory: str | Path, html: bool = False, check_dir: bool = True) -> None:
        self.directory = Path(directory).resolve()
        self.html = html
        if check_dir and not self.directory.is_dir():
            raise RuntimeError(f"StaticFiles directory '{directory}' does not exist")

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        if scope["type"] != "http":
            return
        if scope["method"] not in ("GET", "HEAD"):
            await _send_error(send, 405, _METHOD_NOT_ALLOWED)
            return
        await self._handle(scope, send)

    async def _handle(self, scope: dict[str, Any], send: Any) -> None:
        raw_path: str = scope.get("path", "/")
        # Strip leading slash and normalize
        rel = raw_path.lstrip("/")
        file_path = (self.directory / rel).resolve()

        # Security: prevent path traversal
        try:
            file_path.relative_to(self.directory)
        except ValueError:
            await _send_error(send, 404, _NOT_FOUND)
            return

        # Directory handling
        if file_path.is_dir():
            if self.html:
                file_path = file_path / "index.html"
            else:
                await _send_error(send, 404, _NOT_FOUND)
                return

        if not file_path.is_file():
            await _send_error(send, 404, _NOT_FOUND)
            return

        media_type, encoding = mimetypes.guess_type(str(file_path))
        if media_type is None:
            media_type = "application/octet-stream"

        content = file_path.read_bytes()
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", media_type.encode("latin-1")),
            (b"content-length", str(len(content)).encode()),
        ]
        if encoding:
            headers.append((b"content-encoding", encoding.encode("latin-1")))

        await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send({"type": "http.response.body", "body": content})


async def _send_error(send: Any, status: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", _CT_JSON)],
        }
    )
    await send({"type": "http.response.body", "body": body})
