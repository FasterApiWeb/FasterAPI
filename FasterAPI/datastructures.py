from __future__ import annotations

import tempfile
from typing import BinaryIO


class UploadFile:
    __slots__ = ("filename", "content_type", "file", "_size")

    def __init__(
        self,
        filename: str,
        content_type: str = "application/octet-stream",
        file: BinaryIO | None = None,
    ) -> None:
        self.filename = filename
        self.content_type = content_type
        self.file: BinaryIO = file or tempfile.SpooledTemporaryFile(
            max_size=1024 * 1024,
        )
        self._size: int | None = None

    async def read(self, size: int = -1) -> bytes:
        return self.file.read(size)

    async def write(self, data: bytes) -> int:
        return self.file.write(data)

    async def seek(self, offset: int) -> None:
        self.file.seek(offset)

    async def close(self) -> None:
        self.file.close()

    @property
    def size(self) -> int | None:
        return self._size

    def __repr__(self) -> str:
        return (
            f"UploadFile(filename={self.filename!r}, "
            f"content_type={self.content_type!r})"
        )


class FormData(dict):
    """Dict subclass for form data that may contain UploadFile values."""
    pass
