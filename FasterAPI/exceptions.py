from __future__ import annotations

from typing import Any


class HTTPException(Exception):
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
