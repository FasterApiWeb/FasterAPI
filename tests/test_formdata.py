from __future__ import annotations

import pytest

from FasterAPI.app import Faster
from FasterAPI.datastructures import FormData, UploadFile
from FasterAPI.dependencies import _resolve_handler
from FasterAPI.exceptions import RequestValidationError
from FasterAPI.params import File, Form
from FasterAPI.request import Request


# --------------- helpers ---------------

def _multipart_body(fields: list[tuple[str, str | tuple[str, bytes, str]]]) -> tuple[bytes, str]:
    """Build a multipart/form-data body.

    fields: list of (name, value) for text fields or
            (name, (filename, data, content_type)) for file fields.

    Returns (body_bytes, content_type_header).
    """
    boundary = "----TestBoundary7MA4YWxkTrZu0gW"
    parts: list[bytes] = []

    for name, value in fields:
        if isinstance(value, tuple):
            filename, data, ct = value
            parts.append(
                f"------TestBoundary7MA4YWxkTrZu0gW\r\n"
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: {ct}\r\n"
                f"\r\n".encode("utf-8") + data + b"\r\n"
            )
        else:
            parts.append(
                f"------TestBoundary7MA4YWxkTrZu0gW\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n'
                f"\r\n"
                f"{value}\r\n".encode("utf-8")
            )

    parts.append(b"------TestBoundary7MA4YWxkTrZu0gW--\r\n")
    body = b"".join(parts)
    content_type = f"multipart/form-data; boundary=----TestBoundary7MA4YWxkTrZu0gW"
    return body, content_type


def _make_request(
    *,
    method: str = "POST",
    path: str = "/",
    headers: list[tuple[bytes, bytes]] | None = None,
    query_string: bytes = b"",
    body: bytes = b"",
) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers or [],
        "query_string": query_string,
        "path_params": {},
        "client": ("127.0.0.1", 8000),
    }
    called = False

    async def receive():
        nonlocal called
        if not called:
            called = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


# ==============================
#  UploadFile unit tests
# ==============================

class TestUploadFile:
    @pytest.mark.asyncio
    async def test_read_write_seek(self):
        uf = UploadFile(filename="test.txt", content_type="text/plain")
        await uf.write(b"hello world")
        await uf.seek(0)
        data = await uf.read()
        assert data == b"hello world"
        await uf.close()

    @pytest.mark.asyncio
    async def test_read_partial(self):
        uf = UploadFile(filename="data.bin")
        await uf.write(b"abcdefgh")
        await uf.seek(0)
        chunk = await uf.read(4)
        assert chunk == b"abcd"
        await uf.close()

    def test_repr(self):
        uf = UploadFile(filename="photo.jpg", content_type="image/jpeg")
        assert "photo.jpg" in repr(uf)
        assert "image/jpeg" in repr(uf)

    def test_defaults(self):
        uf = UploadFile(filename="file.bin")
        assert uf.content_type == "application/octet-stream"
        assert uf.headers == {}
        assert uf.size is None

    @pytest.mark.asyncio
    async def test_spooled_temp_file_backend(self):
        import tempfile
        uf = UploadFile(filename="test.txt")
        assert isinstance(uf.file, tempfile.SpooledTemporaryFile)
        await uf.close()


# ==============================
#  FormData unit tests
# ==============================

class TestFormData:
    def test_dict_behavior(self):
        fd = FormData({"name": "Alice", "age": "30"})
        assert fd["name"] == "Alice"
        assert fd.get("missing") is None
        assert len(fd) == 2

    @pytest.mark.asyncio
    async def test_close_upload_files(self):
        uf = UploadFile(filename="test.txt")
        await uf.write(b"data")
        fd = FormData({"file": uf, "name": "test"})
        await fd.close()
        assert uf.file.closed


# ==============================
#  Request.form() — urlencoded
# ==============================

class TestRequestFormUrlencoded:
    @pytest.mark.asyncio
    async def test_urlencoded_basic(self):
        req = _make_request(
            body=b"name=Alice&age=30",
            headers=[(b"content-type", b"application/x-www-form-urlencoded")],
        )
        form = await req.form()
        assert isinstance(form, FormData)
        assert form["name"] == "Alice"
        assert form["age"] == "30"

    @pytest.mark.asyncio
    async def test_urlencoded_empty(self):
        req = _make_request(
            body=b"",
            headers=[(b"content-type", b"application/x-www-form-urlencoded")],
        )
        form = await req.form()
        assert form == {}

    @pytest.mark.asyncio
    async def test_urlencoded_special_chars(self):
        req = _make_request(
            body=b"message=hello+world&path=%2Ffoo%2Fbar",
            headers=[(b"content-type", b"application/x-www-form-urlencoded")],
        )
        form = await req.form()
        assert form["message"] == "hello world"
        assert form["path"] == "/foo/bar"

    @pytest.mark.asyncio
    async def test_form_is_cached(self):
        req = _make_request(
            body=b"x=1",
            headers=[(b"content-type", b"application/x-www-form-urlencoded")],
        )
        form1 = await req.form()
        form2 = await req.form()
        assert form1 is form2


# ==============================
#  Request.form() — multipart
# ==============================

class TestRequestFormMultipart:
    @pytest.mark.asyncio
    async def test_text_fields(self):
        body, ct = _multipart_body([
            ("name", "Alice"),
            ("city", "Wonderland"),
        ])
        req = _make_request(
            body=body,
            headers=[(b"content-type", ct.encode())],
        )
        form = await req.form()
        assert form["name"] == "Alice"
        assert form["city"] == "Wonderland"

    @pytest.mark.asyncio
    async def test_file_upload(self):
        file_content = b"file contents here"
        body, ct = _multipart_body([
            ("doc", ("report.txt", file_content, "text/plain")),
        ])
        req = _make_request(
            body=body,
            headers=[(b"content-type", ct.encode())],
        )
        form = await req.form()
        upload = form["doc"]
        assert isinstance(upload, UploadFile)
        assert upload.filename == "report.txt"
        assert upload.content_type == "text/plain"
        data = await upload.read()
        assert data == file_content
        assert upload.size == len(file_content)
        await upload.close()

    @pytest.mark.asyncio
    async def test_mixed_fields_and_files(self):
        body, ct = _multipart_body([
            ("description", "My photo"),
            ("photo", ("cat.jpg", b"\xff\xd8\xff\xe0", "image/jpeg")),
        ])
        req = _make_request(
            body=body,
            headers=[(b"content-type", ct.encode())],
        )
        form = await req.form()
        assert form["description"] == "My photo"
        upload = form["photo"]
        assert isinstance(upload, UploadFile)
        assert upload.filename == "cat.jpg"
        assert upload.content_type == "image/jpeg"
        data = await upload.read()
        assert data == b"\xff\xd8\xff\xe0"
        await upload.close()

    @pytest.mark.asyncio
    async def test_binary_file(self):
        binary_data = bytes(range(256))
        body, ct = _multipart_body([
            ("blob", ("data.bin", binary_data, "application/octet-stream")),
        ])
        req = _make_request(
            body=body,
            headers=[(b"content-type", ct.encode())],
        )
        form = await req.form()
        upload = form["blob"]
        data = await upload.read()
        assert data == binary_data
        await upload.close()


# ==============================
#  DI: File() descriptor
# ==============================

class TestFileInjection:
    @pytest.mark.asyncio
    async def test_file_with_marker(self):
        async def handler(doc: UploadFile = File()):
            data = await doc.read()
            return {"name": doc.filename, "size": len(data)}

        file_content = b"test file data"
        body, ct = _multipart_body([
            ("doc", ("readme.txt", file_content, "text/plain")),
        ])
        req = _make_request(
            body=body,
            headers=[(b"content-type", ct.encode())],
        )
        result, _ = await _resolve_handler(handler, req, {})
        assert result == {"name": "readme.txt", "size": 14}

    @pytest.mark.asyncio
    async def test_file_by_annotation_alone(self):
        """UploadFile annotation without File() marker should also work."""
        async def handler(photo: UploadFile):
            data = await photo.read()
            return {"name": photo.filename, "len": len(data)}

        body, ct = _multipart_body([
            ("photo", ("cat.png", b"\x89PNG", "image/png")),
        ])
        req = _make_request(
            body=body,
            headers=[(b"content-type", ct.encode())],
        )
        result, _ = await _resolve_handler(handler, req, {})
        assert result == {"name": "cat.png", "len": 4}

    @pytest.mark.asyncio
    async def test_file_missing_raises_validation_error(self):
        async def handler(doc: UploadFile = File()):
            return {}

        body, ct = _multipart_body([("other", "value")])
        req = _make_request(
            body=body,
            headers=[(b"content-type", ct.encode())],
        )
        with pytest.raises(RequestValidationError) as exc_info:
            await _resolve_handler(handler, req, {})
        assert exc_info.value.errors[0]["loc"] == ["body", "doc"]


# ==============================
#  DI: Form() descriptor
# ==============================

class TestFormInjection:
    @pytest.mark.asyncio
    async def test_form_field(self):
        async def handler(username: str = Form()):
            return {"user": username}

        req = _make_request(
            body=b"username=alice",
            headers=[(b"content-type", b"application/x-www-form-urlencoded")],
        )
        result, _ = await _resolve_handler(handler, req, {})
        assert result == {"user": "alice"}

    @pytest.mark.asyncio
    async def test_form_field_default(self):
        async def handler(role: str = Form("guest")):
            return {"role": role}

        req = _make_request(
            body=b"",
            headers=[(b"content-type", b"application/x-www-form-urlencoded")],
        )
        result, _ = await _resolve_handler(handler, req, {})
        assert result == {"role": "guest"}

    @pytest.mark.asyncio
    async def test_form_field_missing_returns_none(self):
        async def handler(missing: str = Form()):
            return {"val": missing}

        req = _make_request(
            body=b"other=1",
            headers=[(b"content-type", b"application/x-www-form-urlencoded")],
        )
        result, _ = await _resolve_handler(handler, req, {})
        assert result == {"val": None}

    @pytest.mark.asyncio
    async def test_form_multipart_text_field(self):
        async def handler(name: str = Form()):
            return {"name": name}

        body, ct = _multipart_body([("name", "Bob")])
        req = _make_request(
            body=body,
            headers=[(b"content-type", ct.encode())],
        )
        result, _ = await _resolve_handler(handler, req, {})
        assert result == {"name": "Bob"}


# ==============================
#  DI: Combined File + Form
# ==============================

class TestCombinedFileForm:
    @pytest.mark.asyncio
    async def test_file_and_form_together(self):
        async def handler(
            title: str = Form(),
            doc: UploadFile = File(),
        ):
            data = await doc.read()
            return {"title": title, "filename": doc.filename, "size": len(data)}

        body, ct = _multipart_body([
            ("title", "My Document"),
            ("doc", ("paper.pdf", b"%PDF-1.4 content", "application/pdf")),
        ])
        req = _make_request(
            body=body,
            headers=[(b"content-type", ct.encode())],
        )
        result, _ = await _resolve_handler(handler, req, {})
        assert result == {"title": "My Document", "filename": "paper.pdf", "size": 16}


# ==============================
#  Full app integration
# ==============================

class TestFormAppIntegration:
    @pytest.mark.asyncio
    async def test_upload_endpoint(self):
        app = Faster(openapi_url=None, docs_url=None, redoc_url=None)

        @app.post("/upload")
        async def upload(file: UploadFile = File(), description: str = Form("none")):
            data = await file.read()
            return {"filename": file.filename, "size": len(data), "desc": description}

        file_content = b"hello world"
        body, ct = _multipart_body([
            ("description", "Test upload"),
            ("file", ("hello.txt", file_content, "text/plain")),
        ])

        sent_messages: list[dict] = []

        async def send(message):
            sent_messages.append(message)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/upload",
            "headers": [(b"content-type", ct.encode())],
            "query_string": b"",
            "path_params": {},
            "client": ("127.0.0.1", 8000),
        }

        body_sent = False

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        await app._handle_http(scope, receive, send)

        import msgspec.json
        assert sent_messages[0]["status"] == 200
        resp = msgspec.json.decode(sent_messages[1]["body"])
        assert resp == {"filename": "hello.txt", "size": 11, "desc": "Test upload"}
