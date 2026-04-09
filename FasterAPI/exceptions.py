from __future__ import annotations

from typing import Any

import msgspec.json


class HTTPException(Exception):
    """An HTTP exception that results in an error response with the given status code."""

    def __init__(
        self,
        status_code: int = 500,
        detail: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.headers = headers

    def __repr__(self) -> str:
        return f"HTTPException(status_code={self.status_code}, detail={self.detail!r})"


class RequestValidationError(Exception):
    """Raised when request data fails validation."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors

    def __repr__(self) -> str:
        return f"RequestValidationError(errors={self.errors!r})"


# --- Default exception handlers ---


async def _default_http_exception_handler(
    request: Any,
    exc: HTTPException,
) -> tuple[int, bytes, list[tuple[bytes, bytes]]]:
    body = msgspec.json.encode({"detail": exc.detail})
    headers: list[tuple[bytes, bytes]] = [(b"content-type", b"application/json")]
    if exc.headers:
        headers.extend((k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in exc.headers.items())
    return exc.status_code, body, headers


async def _default_validation_exception_handler(
    request: Any,
    exc: RequestValidationError,
) -> tuple[int, bytes, list[tuple[bytes, bytes]]]:
    detail = []
    for err in exc.errors:
        detail.append(
            {
                "loc": err.get("loc", []),
                "msg": err.get("msg", ""),
                "type": err.get("type", "value_error"),
            }
        )
    body = msgspec.json.encode({"detail": detail})
    headers: list[tuple[bytes, bytes]] = [(b"content-type", b"application/json")]
    return 422, body, headers
