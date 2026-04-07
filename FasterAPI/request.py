from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import parse_qs, unquote

import msgspec.json


class Request:
    __slots__ = (
        "_scope", "_receive", "_body", "_body_read",
        "method", "path", "headers", "path_params", "query_params",
    )

    def __init__(self, scope: dict, receive: Any) -> None:
        self._scope = scope
        self._receive = receive
        self._body: bytes = b""
        self._body_read: bool = False

        self.method: str = scope.get("method", "GET")
        self.path: str = scope.get("path", "/")
        self.path_params: dict[str, str] = scope.get("path_params", {})

        # Parse headers into a dict (lowercase keys)
        raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        self.headers: dict[str, str] = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in raw_headers
        }

        # Parse query string
        qs = scope.get("query_string", b"").decode("latin-1")
        parsed = parse_qs(qs, keep_blank_values=True)
        self.query_params: dict[str, str] = {
            k: v[0] if len(v) == 1 else v
            for k, v in parsed.items()
        }

    async def _read_body(self) -> bytes:
        if self._body_read:
            return self._body
        parts: list[bytes] = []
        while True:
            message = await self._receive()
            body = message.get("body", b"")
            if body:
                parts.append(body)
            if not message.get("more_body", False):
                break
        self._body = b"".join(parts)
        self._body_read = True
        return self._body

    @property
    def body(self) -> bytes:
        return self._body

    async def json(self) -> Any:
        raw = await self._read_body()
        return msgspec.json.decode(raw)

    async def form(self) -> dict[str, str]:
        raw = await self._read_body()
        ct = self.content_type
        if ct and "multipart/form-data" in ct:
            return self._parse_multipart(raw, ct)
        text = raw.decode("latin-1")
        parsed = parse_qs(text, keep_blank_values=True)
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

    def _parse_multipart(self, raw: bytes, content_type: str) -> dict[str, str]:
        # Extract boundary
        boundary = None
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[len("boundary="):]
                break
        if boundary is None:
            return {}
        boundary_bytes = boundary.encode("latin-1")
        delimiter = b"--" + boundary_bytes
        parts = raw.split(delimiter)
        result: dict[str, str] = {}
        for part in parts:
            part = part.strip(b"\r\n")
            if not part or part == b"--":
                continue
            if b"\r\n\r\n" in part:
                header_section, body = part.split(b"\r\n\r\n", 1)
            elif b"\n\n" in part:
                header_section, body = part.split(b"\n\n", 1)
            else:
                continue
            header_text = header_section.decode("latin-1")
            name = None
            for line in header_text.split("\n"):
                line = line.strip()
                if "name=" in line.lower():
                    # Extract name from Content-Disposition
                    for segment in line.split(";"):
                        segment = segment.strip()
                        if segment.lower().startswith("name="):
                            name = segment[5:].strip('"')
                            break
            if name is not None:
                result[name] = body.rstrip(b"\r\n").decode("utf-8")
        return result

    @property
    def client(self) -> tuple[str, int] | None:
        client = self._scope.get("client")
        if client is None:
            return None
        return (client[0], client[1])

    @property
    def cookies(self) -> dict[str, str]:
        cookie_header = self.headers.get("cookie", "")
        if not cookie_header:
            return {}
        sc = SimpleCookie()
        sc.load(cookie_header)
        return {key: morsel.value for key, morsel in sc.items()}

    @property
    def content_type(self) -> str | None:
        return self.headers.get("content-type")
