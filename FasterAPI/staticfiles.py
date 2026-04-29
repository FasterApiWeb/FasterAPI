"""StaticFiles ASGI application for serving files from a directory."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import stat as stat_mod
from collections.abc import Callable, Sequence
from email.utils import formatdate, parsedate_to_datetime
from pathlib import Path
from secrets import token_hex
from typing import Any

import anyio

__all__ = ["StaticFiles"]

_CT_JSON = b"application/json"
_CT_PLAIN = b"text/plain; charset=utf-8"
_NOT_FOUND = b'{"detail":"Not Found"}'
_METHOD_NOT_ALLOWED = b'{"detail":"Method Not Allowed"}'
_CHUNK_SIZE = 64 * 1024

# Headers preserved on 304 (RFC 7232; aligned with Starlette's NotModifiedResponse)
_NOT_MODIFIED_HEADER_NAMES = frozenset(
    {
        b"cache-control",
        b"content-location",
        b"date",
        b"etag",
        b"expires",
        b"vary",
    }
)


class MalformedRangeHeader(Exception):
    def __init__(self, content: str = "Malformed range header.") -> None:
        self.content = content


class RangeNotSatisfiable(Exception):
    def __init__(self, max_size: int) -> None:
        self.max_size = max_size


def _scope_headers(scope: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_k, raw_v in scope.get("headers", []):
        key = raw_k.decode("latin-1").lower()
        out[key] = raw_v.decode("latin-1")
    return out


def _etag_from_stat(st: os.stat_result) -> str:
    etag_base = str(st.st_mtime) + "-" + str(st.st_size)
    digest = hashlib.md5(etag_base.encode(), usedforsecurity=False).hexdigest()
    return f'"{digest}"'


def _last_modified_http(st: os.stat_result) -> str:
    return formatdate(st.st_mtime, usegmt=True)


def _headers_for_304(full: list[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    return [(k, v) for k, v in full if k.lower() in _NOT_MODIFIED_HEADER_NAMES]


def _check_not_modified(req: dict[str, str], etag: str, last_modified_http: str) -> bool:
    """Return True if the client should receive 304 Not Modified."""
    if nm := req.get("if-none-match"):
        tags = [x.strip() for x in nm.split(",")]
        for tag in tags:
            pure = tag
            if pure.startswith("W/"):
                pure = pure[2:].strip()
            if pure == "*" or pure == etag:
                return True
        return False

    if ims := req.get("if-modified-since"):
        try:
            ims_dt = parsedate_to_datetime(ims)
            lm_dt = parsedate_to_datetime(last_modified_http)
        except (TypeError, ValueError):
            return False
        return lm_dt <= ims_dt

    return False


def _if_range_matches(if_range: str, last_modified_http: str, etag: str) -> bool:
    return if_range in (last_modified_http, etag)


def _parse_ranges(range_: str, file_size: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for part in range_.split(","):
        part = part.strip()
        if not part or part == "-":
            continue
        if "-" not in part:
            continue
        start_str, end_str = part.split("-", 1)
        start_str = start_str.strip()
        end_str = end_str.strip()
        try:
            start = int(start_str) if start_str else file_size - int(end_str)
            end = (
                int(end_str) + 1
                if start_str and end_str and int(end_str) < file_size
                else file_size
            )
            ranges.append((start, end))
        except ValueError:
            continue
    return ranges


def _parse_range_header(http_range: str, file_size: int) -> list[tuple[int, int]]:
    try:
        units, range_ = http_range.split("=", 1)
    except ValueError as exc:
        raise MalformedRangeHeader() from exc

    if units.strip().lower() != "bytes":
        raise MalformedRangeHeader("Only support bytes range")

    ranges = _parse_ranges(range_, file_size)
    if len(ranges) == 0:
        raise MalformedRangeHeader("Range header: range must be requested")

    if any(not (0 <= start < file_size) for start, _ in ranges):
        raise RangeNotSatisfiable(file_size)

    if any(start > end for start, end in ranges):
        raise MalformedRangeHeader("Range header: start must be less than end")

    if len(ranges) == 1:
        return ranges

    ranges.sort()
    merged: list[tuple[int, int]] = [ranges[0]]
    for start, end in ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    return merged


def _multipart_payload_length_and_headers(
    boundary: str,
    content_type: str,
    max_size: int,
    ranges: Sequence[tuple[int, int]],
) -> tuple[int, Callable[[int, int], bytes]]:
    """Return total byte length of multipart body and a header-block factory."""

    def header_block(start: int, end: int) -> bytes:
        return (
            f"--{boundary}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Range: bytes {start}-{end - 1}/{max_size}\r\n"
            "\r\n"
        ).encode("latin-1")

    total = 0
    for start, end in ranges:
        total += len(header_block(start, end))
        total += end - start
        total += 2  # CRLF after each range body (before next part or closing delimiter)
    total += len(f"--{boundary}--".encode("latin-1"))
    return total, header_block


class StaticFiles:
    """Serve static files from a local directory as an ASGI application.

    Behaviour aligns with common Starlette patterns: conditional GET (``ETag`` /
    ``Last-Modified``, ``304 Not Modified``), ``Range`` requests (``206`` including
    multipart byte ranges), ``HEAD`` without a body, and async chunked reads via
    ``anyio``.
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

    def _sync_lookup(self, raw_path: str) -> tuple[Path, os.stat_result] | None:
        """Resolve *raw_path* under ``directory``; return path and stat, or ``None``."""
        rel = raw_path.lstrip("/")
        file_path = (self.directory / rel).resolve()
        try:
            file_path.relative_to(self.directory)
        except ValueError:
            return None
        if file_path.is_dir():
            if self.html:
                file_path = file_path / "index.html"
            else:
                return None
        try:
            st = os.stat(file_path)
        except OSError:
            return None
        if not stat_mod.S_ISREG(st.st_mode):
            return None
        return file_path, st

    def _build_full_headers(
        self,
        file_path: Path,
        st: os.stat_result,
        media_type: str,
        encoding: str | None,
    ) -> list[tuple[bytes, bytes]]:
        etag = _etag_from_stat(st)
        lm = _last_modified_http(st)
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", media_type.encode("latin-1")),
            (b"content-length", str(st.st_size).encode()),
            (b"accept-ranges", b"bytes"),
            (b"etag", etag.encode("latin-1")),
            (b"last-modified", lm.encode("latin-1")),
        ]
        if encoding:
            headers.append((b"content-encoding", encoding.encode("latin-1")))
        return headers

    async def _handle(self, scope: dict[str, Any], send: Any) -> None:
        raw_path: str = scope.get("path", "/")
        looked_up = await anyio.to_thread.run_sync(self._sync_lookup, raw_path)
        if looked_up is None:
            await _send_error(send, 404, _NOT_FOUND)
            return

        file_path, st = looked_up
        media_type, encoding = mimetypes.guess_type(str(file_path))
        if media_type is None:
            media_type = "application/octet-stream"

        etag_http = _etag_from_stat(st)
        lm_http = _last_modified_http(st)
        full_headers = self._build_full_headers(file_path, st, media_type, encoding)

        req = _scope_headers(scope)
        method = scope["method"]

        if _check_not_modified(req, etag_http, lm_http):
            h304 = _headers_for_304(full_headers)
            await send({"type": "http.response.start", "status": 304, "headers": h304})
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

        http_range = req.get("range")
        http_if_range = req.get("if-range")
        use_range = http_range is not None and (
            http_if_range is None or _if_range_matches(http_if_range, lm_http, etag_http)
        )

        if use_range:
            try:
                ranges = _parse_range_header(http_range or "", st.st_size)
            except MalformedRangeHeader as exc:
                await _send_plain(send, 400, exc.content.encode("utf-8"))
                return
            except RangeNotSatisfiable as exc:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 416,
                        "headers": [
                            (b"content-type", _CT_PLAIN),
                            (b"content-range", f"bytes */{exc.max_size}".encode("latin-1")),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": b"", "more_body": False})
                return

            if len(ranges) == 1:
                start, end = ranges[0]
                await self._send_single_range(send, file_path, full_headers, st.st_size, start, end, method)
                return

            await self._send_multipart_ranges(
                send, file_path, full_headers, media_type, st.st_size, ranges, method
            )
            return

        await self._send_full_file(send, file_path, full_headers, method)

    async def _send_full_file(
        self,
        send: Any,
        file_path: Path,
        headers: list[tuple[bytes, bytes]],
        method: str,
    ) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        if method == "HEAD":
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

        async with await anyio.open_file(file_path, "rb") as file:
            more_body = True
            while more_body:
                chunk = await file.read(_CHUNK_SIZE)
                more_body = len(chunk) == _CHUNK_SIZE
                await send({"type": "http.response.body", "body": chunk, "more_body": more_body})

    async def _send_single_range(
        self,
        send: Any,
        file_path: Path,
        base_headers: list[tuple[bytes, bytes]],
        file_size: int,
        start: int,
        end: int,
        method: str,
    ) -> None:
        """Serve ``bytes [start, end)`` with status 206."""
        rh: list[tuple[bytes, bytes]] = []
        for k, v in base_headers:
            if k.lower() in (b"content-length", b"content-range"):
                continue
            rh.append((k, v))
        rh.append((b"content-range", f"bytes {start}-{end - 1}/{file_size}".encode("latin-1")))
        rh.append((b"content-length", str(end - start).encode()))

        await send({"type": "http.response.start", "status": 206, "headers": rh})

        if method == "HEAD":
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

        async with await anyio.open_file(file_path, "rb") as file:
            await file.seek(start)
            pos = start
            while pos < end:
                chunk = await file.read(min(_CHUNK_SIZE, end - pos))
                if not chunk:
                    break
                pos += len(chunk)
                more_body = pos < end
                await send({"type": "http.response.body", "body": chunk, "more_body": more_body})

    async def _send_multipart_ranges(
        self,
        send: Any,
        file_path: Path,
        base_headers: list[tuple[bytes, bytes]],
        media_type: str,
        file_size: int,
        ranges: list[tuple[int, int]],
        method: str,
    ) -> None:
        boundary = token_hex(13)
        mp_len, header_block = _multipart_payload_length_and_headers(boundary, media_type, file_size, ranges)

        out_headers: list[tuple[bytes, bytes]] = []
        for k, v in base_headers:
            if k.lower() in (b"content-length", b"content-type"):
                continue
            out_headers.append((k, v))
        out_headers.append((b"content-type", f"multipart/byteranges; boundary={boundary}".encode("latin-1")))
        out_headers.append((b"content-length", str(mp_len).encode()))

        await send({"type": "http.response.start", "status": 206, "headers": out_headers})

        if method == "HEAD":
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

        async with await anyio.open_file(file_path, "rb") as file:
            for part_start, part_end in ranges:
                await send(
                    {
                        "type": "http.response.body",
                        "body": header_block(part_start, part_end),
                        "more_body": True,
                    }
                )
                await file.seek(part_start)
                pos = part_start
                while pos < part_end:
                    chunk = await file.read(min(_CHUNK_SIZE, part_end - pos))
                    if not chunk:
                        break
                    pos += len(chunk)
                    await send({"type": "http.response.body", "body": chunk, "more_body": True})
                await send({"type": "http.response.body", "body": b"\r\n", "more_body": True})

            await send(
                {
                    "type": "http.response.body",
                    "body": f"--{boundary}--".encode("latin-1"),
                    "more_body": False,
                }
            )


async def _send_plain(send: Any, status: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", _CT_PLAIN), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _send_error(send: Any, status: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", _CT_JSON)],
        }
    )
    await send({"type": "http.response.body", "body": body})
