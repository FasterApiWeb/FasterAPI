from __future__ import annotations

import asyncio
import datetime
import decimal
import mimetypes
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import msgspec.json

from .types import ASGIApp


def _enc_hook(obj: Any) -> Any:
    """Custom encoder for types not natively supported by msgspec."""
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, datetime.date):
        return obj.isoformat()
    if isinstance(obj, datetime.time):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, decimal.Decimal):
        return str(obj)
    raise TypeError(f"Unsupported type: {type(obj)!r}")


def encode_json(content: Any) -> bytes:
    """Encode content to JSON bytes, handling datetime/UUID/Decimal."""
    return msgspec.json.encode(content, enc_hook=_enc_hook)


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
    """Response that serializes content as JSON using msgspec (with datetime/UUID/Decimal support).

    Pass ``bytes``, ``bytearray``, or ``memoryview`` to skip encoding and send **pre-serialised**
    JSON (hot-path optimisation when the payload is fixed at import time or cached externally).
    """

    media_type = "application/json"

    def _render(self, content: Any) -> bytes:
        if isinstance(content, memoryview):
            return bytes(content)
        if isinstance(content, (bytes, bytearray)):
            return bytes(content)
        return encode_json(content)


# ORJSONResponse and UJSONResponse are aliases — msgspec is faster than both.
ORJSONResponse = JSONResponse
UJSONResponse = JSONResponse


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


class EventSourceResponse:
    """Server-Sent Events (SSE) response.

    Streams events to the client in the ``text/event-stream`` format.

    Usage::

        async def event_generator():
            yield {"data": "hello"}
            yield {"event": "update", "data": "world", "id": "1"}

        @app.get("/stream")
        async def stream():
            return EventSourceResponse(event_generator())
    """

    def __init__(
        self,
        content: AsyncIterator[dict[str, str]] | Iterator[dict[str, str]],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        ping_interval: float | None = None,
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.ping_interval = ping_interval

    @staticmethod
    def _format_event(event: dict[str, str] | str) -> bytes:
        if isinstance(event, str):
            return f"data: {event}\n\n".encode()
        lines: list[str] = []
        if "id" in event:
            lines.append(f"id: {event['id']}")
        if "event" in event:
            lines.append(f"event: {event['event']}")
        if "data" in event:
            for line in event["data"].splitlines():
                lines.append(f"data: {line}")
        if "retry" in event:
            lines.append(f"retry: {event['retry']}")
        return ("\n".join(lines) + "\n\n").encode()

    def _build_headers(self) -> list[tuple[bytes, bytes]]:
        raw: list[tuple[bytes, bytes]] = [
            (b"content-type", b"text/event-stream"),
            (b"cache-control", b"no-cache"),
            (b"connection", b"keep-alive"),
            (b"x-accel-buffering", b"no"),
        ]
        for key, value in self.headers.items():
            raw.append((key.lower().encode("latin-1"), value.encode("latin-1")))
        return raw

    async def to_asgi(self, send: ASGIApp) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self._build_headers(),
            }
        )
        if hasattr(self.content, "__aiter__"):
            async for event in self.content:
                chunk = self._format_event(event)
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
        else:
            for event in self.content:
                chunk = self._format_event(event)
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
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
