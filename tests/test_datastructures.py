"""UploadFile and FormData helpers."""

import pytest

from FasterAPI.datastructures import FormData, UploadFile


@pytest.mark.asyncio
async def test_upload_file_read_write_seek(tmp_path):
    u = UploadFile(filename="t.bin", content_type="application/octet-stream")
    n = await u.write(b"hello")
    assert n == 5
    await u.seek(0)
    data = await u.read()
    assert data == b"hello"
    await u.close()


@pytest.mark.asyncio
async def test_upload_file_repr():
    u = UploadFile(filename="a.txt")
    assert "a.txt" in repr(u)


@pytest.mark.asyncio
async def test_form_data_close_closes_files():
    u1 = UploadFile(filename="1")
    await u1.write(b"x")
    fd = FormData({"f": u1, "k": "v"})
    await fd.close()
