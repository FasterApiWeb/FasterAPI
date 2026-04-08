from __future__ import annotations

import tempfile
from typing import IO, Any


class UploadFile:
    """Represents an uploaded file from a multipart/form-data request.

    Uses SpooledTemporaryFile: data stays in memory up to 1 MB, then spills to disk.
    """

    __slots__ = ("filename", "content_type", "file", "headers", "_size")

    def __init__(
        self,
        filename: str,
        content_type: str = "application/octet-stream",
        file: IO[bytes] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.filename = filename
        self.content_type = content_type
        self.file: IO[bytes] = file or tempfile.SpooledTemporaryFile(
            max_size=1024 * 1024,  # 1 MB
        )
        self.headers = headers or {}
        self._size: int | None = None

    async def read(self, size: int = -1) -> bytes:
        """Read up to ``size`` bytes from the file (-1 means read all)."""
        return self.file.read(size)

    async def write(self, data: bytes) -> int:
        """Write data to the file and return the number of bytes written."""
        return self.file.write(data)

    async def seek(self, offset: int) -> None:
        """Seek to the given byte offset in the file."""
        self.file.seek(offset)

    async def close(self) -> None:
        """Close the underlying file."""
        self.file.close()

    @property
    def size(self) -> int | None:
        """Return the file size in bytes, or None if unknown."""
        return self._size

    def __repr__(self) -> str:
        return (
            f"UploadFile(filename={self.filename!r}, "
            f"content_type={self.content_type!r})"
        )


class FormData(dict):
    """Dict subclass for form data that may contain UploadFile values."""

    async def close(self) -> None:
        """Close all UploadFile instances in this form data."""
        for value in self.values():
            if isinstance(value, UploadFile):
                await value.close()
