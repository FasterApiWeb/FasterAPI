"""Tests for response classes and ASGI emitters."""

from pathlib import Path

import pytest
from FasterAPI.response import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)


@pytest.mark.asyncio
async def test_response_bytes_and_headers():
    sent: list[dict] = []

    async def send(msg: dict) -> None:
        sent.append(msg)

    r = Response(b"hi", status_code=201, headers={"X-Test": "1"}, media_type="application/octet-stream")
    await r.to_asgi(send)
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 201
    hdrs = dict(sent[0]["headers"])
    assert hdrs[b"content-type"] == b"application/octet-stream"
    assert hdrs[b"x-test"] == b"1"
    assert sent[1]["body"] == b"hi"


@pytest.mark.asyncio
async def test_response_text_charset():
    sent: list[dict] = []

    async def send(msg: dict) -> None:
        sent.append(msg)

    r = Response("ë", media_type="text/plain")
    await r.to_asgi(send)
    hdrs = dict(sent[0]["headers"])
    assert b"charset=utf-8" in hdrs[b"content-type"]


@pytest.mark.asyncio
async def test_json_response():
    sent: list[dict] = []

    async def send(msg: dict) -> None:
        sent.append(msg)

    await JSONResponse({"a": 1}).to_asgi(send)
    assert b"application/json" in sent[0]["headers"][0][1]


@pytest.mark.asyncio
async def test_html_plain_redirect():
    for cls, body in [(HTMLResponse, "<p>x</p>"), (PlainTextResponse, "ok")]:
        sent: list[dict] = []

        async def send(msg: dict) -> None:
            sent.append(msg)

        await cls(body).to_asgi(send)
        assert sent[1]["body"] == body.encode()

    sent2: list[dict] = []

    async def send2(msg: dict) -> None:
        sent2.append(msg)

    await RedirectResponse("/there", 302).to_asgi(send2)
    assert sent2[0]["status"] == 302
    assert dict(sent2[0]["headers"])[b"location"] == b"/there"


@pytest.mark.asyncio
async def test_streaming_response_sync_iter():
    sent: list[dict] = []

    async def send(msg: dict) -> None:
        sent.append(msg)

    async def body():
        yield b"a"
        yield b"b"

    # async iterator path
    await StreamingResponse(body(), media_type="text/plain").to_asgi(send)
    assert any(m.get("body") == b"a" and m.get("more_body") for m in sent)


@pytest.mark.asyncio
async def test_streaming_response_sync_for():
    sent: list[dict] = []

    async def send(msg: dict) -> None:
        sent.append(msg)

    def gen():
        yield b"x"
        yield b"y"

    await StreamingResponse(gen(), media_type="application/octet-stream").to_asgi(send)
    parts = [m["body"] for m in sent if m["type"] == "http.response.body" and m.get("body")]
    assert b"".join(parts) == b"xy"


@pytest.mark.asyncio
async def test_file_response(tmp_path: Path):
    p = tmp_path / "x.txt"
    p.write_text("file-content")
    sent: list[dict] = []

    async def send(msg: dict) -> None:
        sent.append(msg)

    await FileResponse(p, filename="dl.txt").to_asgi(send)
    assert sent[1]["body"] == b"file-content"
    hdrs = dict(sent[0]["headers"])
    assert b"attachment" in hdrs[b"content-disposition"]
