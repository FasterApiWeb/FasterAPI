from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import parse_qs

import msgspec.json
from python_multipart.multipart import parse_options_header, MultipartParser

from .datastructures import FormData, UploadFile


class Request:
    """Represents an incoming HTTP request."""

    __slots__ = (
        "_scope", "_receive", "_body", "_body_read", "_form_cache",
        "method", "path", "headers", "path_params", "query_params",
    )

    def __init__(self, scope: dict, receive: Any) -> None:
        self._scope = scope
        self._receive = receive
        self._body: bytes = b""
        self._body_read: bool = False
        self._form_cache: FormData | None = None

        self.method: str = scope.get("method", "GET")
        self.path: str = scope.get("path", "/")
        self.path_params: dict[str, str] = scope.get("path_params", {})

        raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        self.headers: dict[str, str] = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in raw_headers
        }

        qs = scope.get("query_string", b"").decode("latin-1")
        parsed = parse_qs(qs, keep_blank_values=True)
        self.query_params: dict[str, Any] = {
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
        """Return the already-read request body bytes."""
        return self._body

    async def json(self) -> Any:
        """Read the request body and parse it as JSON."""
        raw = await self._read_body()
        return msgspec.json.decode(raw)

    async def form(self) -> FormData:
        """Read the request body and parse it as form data."""
        if self._form_cache is not None:
            return self._form_cache

        raw = await self._read_body()
        ct = self.content_type or ""

        if "multipart/form-data" in ct:
            result = _parse_multipart(raw, ct)
        else:
            result = _parse_urlencoded(raw)

        self._form_cache = result
        return result

    @property
    def client(self) -> tuple[str, int] | None:
        """Return the client's (host, port) tuple, or None if unavailable."""
        client = self._scope.get("client")
        if client is None:
            return None
        return (client[0], client[1])

    @property
    def cookies(self) -> dict[str, str]:
        """Parse and return cookies from the request headers."""
        cookie_header = self.headers.get("cookie", "")
        if not cookie_header:
            return {}
        sc = SimpleCookie()
        sc.load(cookie_header)
        return {key: morsel.value for key, morsel in sc.items()}

    @property
    def content_type(self) -> str | None:
        """Return the Content-Type header value, or None if not set."""
        return self.headers.get("content-type")


def _parse_urlencoded(raw: bytes) -> FormData:
    text = raw.decode("latin-1")
    parsed = parse_qs(text, keep_blank_values=True)
    return FormData({k: v[0] if len(v) == 1 else v for k, v in parsed.items()})


def _parse_multipart(raw: bytes, content_type: str) -> FormData:
    """Parse multipart/form-data using python-multipart's streaming parser."""
    _, params = parse_options_header(content_type)
    boundary = params.get(b"boundary", b"")

    # State shared across callbacks
    header_field = bytearray()
    header_value = bytearray()
    current_headers: dict[str, str] = {}
    current_data = bytearray()
    fields: dict[str, str | UploadFile] = {}

    # Per-part tracking
    part_info: dict[str, Any] = {}

    def on_part_begin() -> None:
        header_field.clear()
        header_value.clear()
        current_headers.clear()
        current_data.clear()
        part_info.clear()

    def on_header_field(data: bytes, start: int, end: int) -> None:
        header_field.extend(data[start:end])

    def on_header_value(data: bytes, start: int, end: int) -> None:
        header_value.extend(data[start:end])

    def on_header_end() -> None:
        field_name = bytes(header_field).decode("latin-1").lower()
        field_val = bytes(header_value).decode("latin-1")
        current_headers[field_name] = field_val
        header_field.clear()
        header_value.clear()

    def on_headers_finished() -> None:
        disposition = current_headers.get("content-disposition", "")
        _, disp_params = parse_options_header(disposition)
        name = disp_params.get(b"name", b"").decode("utf-8")
        filename = disp_params.get(b"filename")
        part_info["name"] = name
        if filename is not None:
            part_info["filename"] = filename.decode("utf-8")
            part_info["content_type"] = current_headers.get(
                "content-type", "application/octet-stream",
            )
        part_info["headers"] = dict(current_headers)

    def on_part_data(data: bytes, start: int, end: int) -> None:
        current_data.extend(data[start:end])

    def on_part_end() -> None:
        name = part_info.get("name", "")
        if not name:
            return
        filename = part_info.get("filename")
        if filename is not None:
            upload = UploadFile(
                filename=filename,
                content_type=part_info.get("content_type", "application/octet-stream"),
                headers=part_info.get("headers", {}),
            )
            upload.file.write(bytes(current_data))
            upload.file.seek(0)
            upload._size = len(current_data)
            fields[name] = upload
        else:
            fields[name] = bytes(current_data).decode("utf-8")

    callbacks = {
        "on_part_begin": on_part_begin,
        "on_header_field": on_header_field,
        "on_header_value": on_header_value,
        "on_header_end": on_header_end,
        "on_headers_finished": on_headers_finished,
        "on_part_data": on_part_data,
        "on_part_end": on_part_end,
    }

    parser = MultipartParser(boundary, callbacks)  # type: ignore[arg-type]
    parser.write(raw)
    parser.finalize()

    return FormData(fields)
