from __future__ import annotations

import asyncio
import mimetypes
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import msgspec.json

from .types import ASGIApp


class Response:
    """Base HTTP response class."""

    media_type: str | None = None
    charset: str = "utf-8"

    def __init__(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        if media_type is not None:
            self.media_type = media_type
        self.body = self._render(content)

    def _render(self, content: Any) -> bytes:
        if content is None:
            return b""
        if isinstance(content, bytes):
            return content
        return bytes(content.encode(self.charset))

    def _build_headers(self) -> list[tuple[bytes, bytes]]:
        raw: list[tuple[bytes, bytes]] = []
        if self.media_type is not None:
            ct = self.media_type
            if self.charset and "text" in ct:
                ct = f"{ct}; charset={self.charset}"
            raw.append((b"content-type", ct.encode("latin-1")))
        for key, value in self.headers.items():
            raw.append((key.lower().encode("latin-1"), value.encode("latin-1")))
        return raw

    async def to_asgi(self, send: ASGIApp) -> None:
        """Send the response through the ASGI interface."""
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self._build_headers(),
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": self.body,
            }
        )


class JSONResponse(Response):
    """Response that serializes content as JSON using msgspec."""

    media_type = "application/json"

    def _render(self, content: Any) -> bytes:
        return msgspec.json.encode(content)


class HTMLResponse(Response):
    """Response with HTML content type."""

    media_type = "text/html"

    def __init__(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(content, status_code, headers)


class PlainTextResponse(Response):
    """Response with plain text content type."""

    media_type = "text/plain"

    def __init__(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(content, status_code, headers)


class RedirectResponse(Response):
    """Response that redirects to a different URL."""

    def __init__(
        self,
        url: str,
        status_code: int = 307,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(b"", status_code, headers)
        self.headers["location"] = url

    def _render(self, content: Any) -> bytes:
        if isinstance(content, bytes):
            return content
        return b""


class StreamingResponse:
    """Response that streams content from an async or sync iterator."""

    def __init__(
        self,
        content: AsyncIterator[bytes] | Iterator[bytes],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.media_type = media_type

    def _build_headers(self) -> list[tuple[bytes, bytes]]:
        raw: list[tuple[bytes, bytes]] = []
        if self.media_type is not None:
            raw.append((b"content-type", self.media_type.encode("latin-1")))
        for key, value in self.headers.items():
            raw.append((key.lower().encode("latin-1"), value.encode("latin-1")))
        return raw

    async def to_asgi(self, send: ASGIApp) -> None:
        """Stream the response body through the ASGI interface."""
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self._build_headers(),
            }
        )
        if hasattr(self.content, "__aiter__"):
            async for chunk in self.content:
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk if isinstance(chunk, bytes) else chunk.encode(),
                        "more_body": True,
                    }
                )
        else:
            for chunk in self.content:
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk if isinstance(chunk, bytes) else chunk.encode(),
                        "more_body": True,
                    }
                )
        await send({"type": "http.response.body", "body": b"", "more_body": False})


class FileResponse:
    """Response that sends a file as an attachment."""

    def __init__(
        self,
        path: str | Path,
        filename: str | None = None,
        media_type: str | None = None,
        headers: dict[str, str] | None = None,
        status_code: int = 200,
    ) -> None:
        self.path = Path(path)
        self.filename = filename or self.path.name
        self.status_code = status_code
        self.headers = headers or {}
        if media_type is not None:
            self.media_type = media_type
        else:
            mt, _ = mimetypes.guess_type(str(self.path))
            self.media_type = mt or "application/octet-stream"

    def _build_headers(self) -> list[tuple[bytes, bytes]]:
        raw: list[tuple[bytes, bytes]] = [
            (b"content-type", self.media_type.encode("latin-1")),
            (
                b"content-disposition",
                f'attachment; filename="{self.filename}"'.encode("latin-1"),
            ),
        ]
        for key, value in self.headers.items():
            raw.append((key.lower().encode("latin-1"), value.encode("latin-1")))
        return raw

    async def to_asgi(self, send: ASGIApp) -> None:
        """Read the file and send it through the ASGI interface."""
        content = await asyncio.get_running_loop().run_in_executor(
            None,
            self.path.read_bytes,
        )
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self._build_headers(),
            }
        )
        await send({"type": "http.response.body", "body": content})
