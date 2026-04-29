"""Optimised HTTP request object for FasterAPI.

Key optimisations:
  - __slots__ throughout to eliminate per-instance __dict__
  - Headers and query params are parsed lazily on first access
  - Body bytes are cached after first full read (unless ``stream_body_no_buffer``)
  - Optional streaming body / streaming multipart for large uploads
  - Cookies are parsed once and cached
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from http.cookies import SimpleCookie
from typing import Any, cast
from urllib.parse import parse_qs

import msgspec.json
from python_multipart.multipart import MultipartParser, parse_options_header

from .datastructures import FormData, UploadFile
from .exceptions import HTTPException
from .types import ASGIApp

__all__ = ["Request"]


class Request:
    """Represents an incoming HTTP request with lazy attribute parsing."""

    __slots__ = (
        "_scope",
        "_receive",
        "_body",
        "_body_read",
        "_form_cache",
        "_headers",
        "_query_params",
        "_cookies",
        "_max_body_size",
        "_stream_no_buffer",
        "method",
        "path",
        "path_params",
    )

    def __init__(self, scope: dict[str, Any], receive: ASGIApp) -> None:
        self._scope = scope
        self._receive = receive
        self._body: bytes = b""
        self._body_read: bool = False
        self._form_cache: FormData | None = None
        self._headers: dict[str, str] | None = None
        self._query_params: dict[str, Any] | None = None
        self._cookies: dict[str, str] | None = None

        st = scope.setdefault("state", {})
        self._max_body_size = st.get("max_body_size")
        self._stream_no_buffer = bool(st.get("stream_body_no_buffer"))

        self.method: str = scope.get("method", "GET")
        self.path: str = scope.get("path", "/")
        self.path_params: dict[str, str] = scope.get("path_params", {})

    @property
    def state(self) -> dict[str, Any]:
        """Mutable per-request state (ASGI ``scope["state"]``)."""
        return self._scope.setdefault("state", {})

    # ------------------------------------------------------------------
    #  Lazy-parsed properties (only computed when first accessed)
    # ------------------------------------------------------------------

    @property
    def headers(self) -> dict[str, str]:
        h = self._headers
        if h is None:
            raw: list[tuple[bytes, bytes]] = self._scope.get("headers", [])
            h = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in raw}
            self._headers = h
        return h

    @property
    def query_params(self) -> dict[str, Any]:
        qp = self._query_params
        if qp is None:
            qs = self._scope.get("query_string", b"").decode("latin-1")
            if qs:
                parsed = parse_qs(qs, keep_blank_values=True)
                qp = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
            else:
                qp = {}
            self._query_params = qp
        return qp

    @property
    def cookies(self) -> dict[str, str]:
        c = self._cookies
        if c is None:
            cookie_header = self.headers.get("cookie", "")
            if cookie_header:
                sc = SimpleCookie()
                sc.load(cookie_header)
                c = {key: morsel.value for key, morsel in sc.items()}
            else:
                c = {}
            self._cookies = c
        return c

    @property
    def content_type(self) -> str | None:
        return self.headers.get("content-type")

    @property
    def client(self) -> tuple[str, int] | None:
        val = self._scope.get("client")
        return (val[0], val[1]) if val is not None else None

    @property
    def body(self) -> bytes:
        return self._body

    # ------------------------------------------------------------------
    #  Body reading
    # ------------------------------------------------------------------

    def _enforce_limit(self, total_so_far: int, chunk_len: int) -> None:
        if self._max_body_size is None:
            return
        if total_so_far + chunk_len > self._max_body_size:
            raise HTTPException(status_code=413, detail="Request entity too large")

    async def stream(self) -> AsyncIterator[bytes]:
        """Yield body chunks from the ASGI ``receive`` channel.

        When ``Faster(stream_request_body=False)`` (default), chunks are also
        concatenated so :meth:`body`, :meth:`json`, and :meth:`form` still work.

        With ``stream_request_body=True``, bytes are **not** retained after
        iteration—use this for large uploads written straight to disk.
        """
        if self._body_read:
            if self._body:
                yield self._body
            return

        buffer_chunks: list[bytes] = []
        total = 0
        try:
            while True:
                message = await self._receive()
                chunk = message.get("body", b"")
                self._enforce_limit(total, len(chunk))
                total += len(chunk)
                if not self._stream_no_buffer and chunk:
                    buffer_chunks.append(chunk)
                if chunk:
                    yield chunk
                if not message.get("more_body", False):
                    break
        finally:
            self._body_read = True
            if not self._stream_no_buffer:
                self._body = b"".join(buffer_chunks)
            else:
                self._body = b""

    async def _read_body(self) -> bytes:
        if self._body_read:
            return self._body
        async for _ in self.stream():
            pass
        return self._body

    async def json(self) -> Any:
        """Read the request body and decode as JSON via msgspec (zero-copy)."""
        raw = await self._read_body()
        return msgspec.json.decode(raw)

    async def form(self) -> FormData:
        """Read the request body and parse as form / multipart data."""
        if self._form_cache is not None:
            return self._form_cache
        ct = self.content_type or ""

        if "multipart/form-data" in ct and self.state.get("stream_multipart"):
            self._form_cache = await self._parse_multipart_stream(ct)
            return self._form_cache

        raw = await self._read_body()
        result = _parse_multipart(raw, ct) if "multipart/form-data" in ct else _parse_urlencoded(raw)
        self._form_cache = result
        return result

    async def _parse_multipart_stream(self, content_type: str) -> FormData:
        """Parse multipart by feeding ASGI chunks into ``MultipartParser`` (no full-body buffer)."""
        _, params = parse_options_header(content_type)
        boundary = params.get(b"boundary", b"")

        header_field = bytearray()
        header_value = bytearray()
        current_headers: dict[str, str] = {}
        current_data = bytearray()
        fields: dict[str, str | UploadFile] = {}
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
            current_headers[bytes(header_field).decode("latin-1").lower()] = bytes(header_value).decode("latin-1")
            header_field.clear()
            header_value.clear()

        def on_headers_finished() -> None:
            disposition = current_headers.get("content-disposition", "")
            _, disp_params = parse_options_header(disposition)
            part_info["name"] = disp_params.get(b"name", b"").decode("utf-8")
            filename = disp_params.get(b"filename")
            if filename is not None:
                part_info["filename"] = filename.decode("utf-8")
                part_info["content_type"] = current_headers.get(
                    "content-type",
                    "application/octet-stream",
                )
                part_info["headers"] = dict(current_headers)
                part_info["upload"] = UploadFile(
                    filename=part_info["filename"],
                    content_type=part_info["content_type"],
                    headers=part_info["headers"],
                )
                part_info["is_file"] = True
            else:
                part_info["is_file"] = False
                part_info["headers"] = dict(current_headers)

        def on_part_data(data: bytes, start: int, end: int) -> None:
            sl = data[start:end]
            if part_info.get("is_file") and "upload" in part_info:
                part_info["upload"].file.write(sl)
            else:
                current_data.extend(sl)

        def on_part_end() -> None:
            name = part_info.get("name", "")
            if not name:
                return
            if part_info.get("is_file") and "upload" in part_info:
                upload = part_info["upload"]
                upload.file.seek(0, 2)
                upload._size = upload.file.tell()
                upload.file.seek(0)
                fields[name] = upload
            else:
                fields[name] = bytes(current_data).decode("utf-8")

        parser = MultipartParser(
            boundary,
            cast(
                Any,
                {
                    "on_part_begin": on_part_begin,
                    "on_header_field": on_header_field,
                    "on_header_value": on_header_value,
                    "on_header_end": on_header_end,
                    "on_headers_finished": on_headers_finished,
                    "on_part_data": on_part_data,
                    "on_part_end": on_part_end,
                },
            ),
        )

        total = 0
        while True:
            message = await self._receive()
            chunk = message.get("body", b"")
            self._enforce_limit(total, len(chunk))
            total += len(chunk)
            if chunk:
                parser.write(chunk)
            if not message.get("more_body", False):
                break

        parser.finalize()
        self._body_read = True
        self._body = b""
        return FormData(fields)


# ------------------------------------------------------------------
#  Form parsing helpers
# ------------------------------------------------------------------


def _parse_urlencoded(raw: bytes) -> FormData:
    text = raw.decode("latin-1")
    parsed = parse_qs(text, keep_blank_values=True)
    return FormData({k: v[0] if len(v) == 1 else v for k, v in parsed.items()})


def _parse_multipart(raw: bytes, content_type: str) -> FormData:
    """Parse multipart/form-data using python-multipart's parser (buffered *raw* body)."""
    _, params = parse_options_header(content_type)
    boundary = params.get(b"boundary", b"")

    header_field = bytearray()
    header_value = bytearray()
    current_headers: dict[str, str] = {}
    current_data = bytearray()
    fields: dict[str, str | UploadFile] = {}
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
        current_headers[bytes(header_field).decode("latin-1").lower()] = bytes(header_value).decode("latin-1")
        header_field.clear()
        header_value.clear()

    def on_headers_finished() -> None:
        disposition = current_headers.get("content-disposition", "")
        _, disp_params = parse_options_header(disposition)
        part_info["name"] = disp_params.get(b"name", b"").decode("utf-8")
        filename = disp_params.get(b"filename")
        if filename is not None:
            part_info["filename"] = filename.decode("utf-8")
            part_info["content_type"] = current_headers.get(
                "content-type",
                "application/octet-stream",
            )
            part_info["headers"] = dict(current_headers)
            part_info["upload"] = UploadFile(
                filename=part_info["filename"],
                content_type=part_info["content_type"],
                headers=part_info["headers"],
            )
            part_info["is_file"] = True
        else:
            part_info["is_file"] = False

    def on_part_data(data: bytes, start: int, end: int) -> None:
        sl = data[start:end]
        if part_info.get("is_file") and "upload" in part_info:
            part_info["upload"].file.write(sl)
        else:
            current_data.extend(sl)

    def on_part_end() -> None:
        name = part_info.get("name", "")
        if not name:
            return
        if part_info.get("is_file") and "upload" in part_info:
            upload = part_info["upload"]
            upload.file.seek(0, 2)
            upload._size = upload.file.tell()
            upload.file.seek(0)
            fields[name] = upload
        else:
            fields[name] = bytes(current_data).decode("utf-8")

    parser = MultipartParser(
        boundary,
        cast(
            Any,
            {
                "on_part_begin": on_part_begin,
                "on_header_field": on_header_field,
                "on_header_value": on_header_value,
                "on_header_end": on_header_end,
                "on_headers_finished": on_headers_finished,
                "on_part_data": on_part_data,
                "on_part_end": on_part_end,
            },
        ),
    )
    parser.write(raw)
    parser.finalize()
    return FormData(fields)
