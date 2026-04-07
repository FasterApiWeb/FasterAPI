import asyncio
import tempfile
from pathlib import Path

import msgspec
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


# --------------- helpers ---------------

class MockSend:
    """Collects ASGI send() calls."""

    def __init__(self):
        self.messages: list[dict] = []

    async def __call__(self, message: dict) -> None:
        self.messages.append(message)

    @property
    def start(self) -> dict:
        return self.messages[0]

    @property
    def body_message(self) -> dict:
        return self.messages[1]

    @property
    def status(self) -> int:
        return self.start["status"]

    @property
    def body(self) -> bytes:
        return self.body_message["body"]

    def header(self, name: str) -> str | None:
        for k, v in self.start["headers"]:
            if k == name.encode("latin-1"):
                return v.decode("latin-1")
        return None


# ==============================
#  Response (base)
# ==============================

class TestResponse:
    @pytest.mark.asyncio
    async def test_bytes_content(self):
        send = MockSend()
        r = Response(b"raw bytes", media_type="application/octet-stream")
        await r.to_asgi(send)
        assert send.status == 200
        assert send.body == b"raw bytes"

    @pytest.mark.asyncio
    async def test_string_content(self):
        send = MockSend()
        r = Response("hello", media_type="text/plain")
        await r.to_asgi(send)
        assert send.body == b"hello"
        assert "text/plain" in send.header("content-type")

    @pytest.mark.asyncio
    async def test_none_content(self):
        send = MockSend()
        r = Response(None, status_code=204)
        await r.to_asgi(send)
        assert send.status == 204
        assert send.body == b""

    @pytest.mark.asyncio
    async def test_custom_headers(self):
        send = MockSend()
        r = Response("ok", media_type="text/plain", headers={"X-Custom": "val"})
        await r.to_asgi(send)
        assert send.header("x-custom") == "val"

    @pytest.mark.asyncio
    async def test_custom_status_code(self):
        send = MockSend()
        r = Response("created", status_code=201, media_type="text/plain")
        await r.to_asgi(send)
        assert send.status == 201


# ==============================
#  JSONResponse
# ==============================

class TestJSONResponse:
    @pytest.mark.asyncio
    async def test_dict(self):
        send = MockSend()
        r = JSONResponse({"key": "value"})
        await r.to_asgi(send)
        assert send.status == 200
        assert msgspec.json.decode(send.body) == {"key": "value"}
        assert send.header("content-type") == "application/json"

    @pytest.mark.asyncio
    async def test_list(self):
        send = MockSend()
        r = JSONResponse([1, 2, 3])
        await r.to_asgi(send)
        assert msgspec.json.decode(send.body) == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_custom_status(self):
        send = MockSend()
        r = JSONResponse({"id": 1}, status_code=201)
        await r.to_asgi(send)
        assert send.status == 201

    @pytest.mark.asyncio
    async def test_custom_headers(self):
        send = MockSend()
        r = JSONResponse({"ok": True}, headers={"X-Request-Id": "abc"})
        await r.to_asgi(send)
        assert send.header("x-request-id") == "abc"


# ==============================
#  HTMLResponse
# ==============================

class TestHTMLResponse:
    @pytest.mark.asyncio
    async def test_html(self):
        send = MockSend()
        r = HTMLResponse("<h1>Hello</h1>")
        await r.to_asgi(send)
        assert send.body == b"<h1>Hello</h1>"
        assert "text/html" in send.header("content-type")

    @pytest.mark.asyncio
    async def test_html_status(self):
        send = MockSend()
        r = HTMLResponse("<p>Not Found</p>", status_code=404)
        await r.to_asgi(send)
        assert send.status == 404


# ==============================
#  PlainTextResponse
# ==============================

class TestPlainTextResponse:
    @pytest.mark.asyncio
    async def test_text(self):
        send = MockSend()
        r = PlainTextResponse("hello world")
        await r.to_asgi(send)
        assert send.body == b"hello world"
        assert "text/plain" in send.header("content-type")


# ==============================
#  RedirectResponse
# ==============================

class TestRedirectResponse:
    @pytest.mark.asyncio
    async def test_redirect_307(self):
        send = MockSend()
        r = RedirectResponse("/new-location")
        await r.to_asgi(send)
        assert send.status == 307
        assert send.header("location") == "/new-location"
        assert send.body == b""

    @pytest.mark.asyncio
    async def test_redirect_301(self):
        send = MockSend()
        r = RedirectResponse("/permanent", status_code=301)
        await r.to_asgi(send)
        assert send.status == 301

    @pytest.mark.asyncio
    async def test_redirect_external(self):
        send = MockSend()
        r = RedirectResponse("https://example.com")
        await r.to_asgi(send)
        assert send.header("location") == "https://example.com"


# ==============================
#  StreamingResponse
# ==============================

class TestStreamingResponse:
    @pytest.mark.asyncio
    async def test_sync_iterator(self):
        def gen():
            yield b"chunk1"
            yield b"chunk2"

        send = MockSend()
        r = StreamingResponse(gen(), media_type="text/plain")
        await r.to_asgi(send)

        assert send.messages[0]["status"] == 200
        assert send.header("content-type") == "text/plain"
        # body chunks + final empty
        body_parts = [m["body"] for m in send.messages[1:]]
        assert b"chunk1" in body_parts
        assert b"chunk2" in body_parts
        assert send.messages[-1]["more_body"] is False

    @pytest.mark.asyncio
    async def test_async_iterator(self):
        async def gen():
            yield b"async1"
            yield b"async2"

        send = MockSend()
        r = StreamingResponse(gen())
        await r.to_asgi(send)

        body_parts = [m["body"] for m in send.messages[1:]]
        assert b"async1" in body_parts
        assert b"async2" in body_parts

    @pytest.mark.asyncio
    async def test_string_chunks(self):
        def gen():
            yield "text1"
            yield "text2"

        send = MockSend()
        r = StreamingResponse(gen(), media_type="text/plain")
        await r.to_asgi(send)

        body_parts = [m["body"] for m in send.messages[1:]]
        assert b"text1" in body_parts

    @pytest.mark.asyncio
    async def test_custom_headers(self):
        def gen():
            yield b""

        send = MockSend()
        r = StreamingResponse(gen(), headers={"X-Stream": "true"})
        await r.to_asgi(send)
        assert send.header("x-stream") == "true"


# ==============================
#  FileResponse
# ==============================

class TestFileResponse:
    @pytest.mark.asyncio
    async def test_file_read(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"file content here")
            path = f.name

        send = MockSend()
        r = FileResponse(path)
        await r.to_asgi(send)

        assert send.status == 200
        assert send.body == b"file content here"
        assert "text/plain" in send.header("content-type")
        assert "attachment" in send.header("content-disposition")
        Path(path).unlink()

    @pytest.mark.asyncio
    async def test_custom_filename(self):
        with tempfile.NamedTemporaryFile(suffix=".dat", delete=False) as f:
            f.write(b"data")
            path = f.name

        send = MockSend()
        r = FileResponse(path, filename="download.bin", media_type="application/octet-stream")
        await r.to_asgi(send)

        assert 'filename="download.bin"' in send.header("content-disposition")
        assert send.header("content-type") == "application/octet-stream"
        Path(path).unlink()

    @pytest.mark.asyncio
    async def test_json_file_mimetype(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b'{"a":1}')
            path = f.name

        send = MockSend()
        r = FileResponse(path)
        await r.to_asgi(send)

        assert "json" in send.header("content-type")
        Path(path).unlink()


# ==============================
#  Response used inside app dispatch
# ==============================

class TestResponseInAppDispatch:
    """Test that returning a Response from a handler bypasses default serialization."""

    @pytest.mark.asyncio
    async def test_json_response_from_handler(self):
        from FasterAPI.app import Faster

        app = Faster()

        @app.get("/json")
        async def handler():
            return JSONResponse({"msg": "custom"}, status_code=201)

        send = MockSend()
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/json",
            "headers": [],
            "query_string": b"",
        }
        called = False
        async def receive():
            nonlocal called
            if not called:
                called = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        await app(scope, receive, send)

        assert send.status == 201
        assert msgspec.json.decode(send.body) == {"msg": "custom"}

    @pytest.mark.asyncio
    async def test_html_response_from_handler(self):
        from FasterAPI.app import Faster

        app = Faster()

        @app.get("/page")
        async def handler():
            return HTMLResponse("<h1>Hi</h1>")

        send = MockSend()
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/page",
            "headers": [],
            "query_string": b"",
        }
        called = False
        async def receive():
            nonlocal called
            if not called:
                called = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        await app(scope, receive, send)

        assert send.body == b"<h1>Hi</h1>"
        assert "text/html" in send.header("content-type")
