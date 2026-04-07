import msgspec
import pytest

from FasterAPI.app import Faster
from FasterAPI.exceptions import HTTPException, RequestValidationError


# --------------- helpers ---------------

class MockSend:
    def __init__(self):
        self.messages: list[dict] = []

    async def __call__(self, message: dict) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int:
        return self.messages[0]["status"]

    @property
    def body(self) -> bytes:
        return self.messages[1]["body"]

    @property
    def json(self) -> dict:
        return msgspec.json.decode(self.body)

    def header(self, name: str) -> str | None:
        for k, v in self.messages[0]["headers"]:
            if k == name.encode("latin-1"):
                return v.decode("latin-1")
        return None


def _make_scope(method: str = "GET", path: str = "/") -> dict:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "query_string": b"",
    }


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


# ==============================
#  HTTPException format
# ==============================

class TestHTTPExceptionFormat:
    @pytest.mark.asyncio
    async def test_404_not_found(self):
        app = Faster()
        send = MockSend()
        await app(_make_scope(path="/nonexistent"), _receive, send)

        assert send.status == 404
        assert send.json == {"detail": "Not Found"}

    @pytest.mark.asyncio
    async def test_handler_raises_http_exception(self):
        app = Faster()

        @app.get("/fail")
        async def handler():
            raise HTTPException(status_code=403, detail="Forbidden")

        send = MockSend()
        await app(_make_scope(path="/fail"), _receive, send)

        assert send.status == 403
        assert send.json == {"detail": "Forbidden"}
        assert send.header("content-type") == "application/json"

    @pytest.mark.asyncio
    async def test_http_exception_with_headers(self):
        app = Faster()

        @app.get("/auth")
        async def handler():
            raise HTTPException(
                status_code=401,
                detail="Unauthorized",
                headers={"WWW-Authenticate": "Bearer"},
            )

        send = MockSend()
        await app(_make_scope(path="/auth"), _receive, send)

        assert send.status == 401
        assert send.json == {"detail": "Unauthorized"}
        assert send.header("www-authenticate") == "Bearer"

    @pytest.mark.asyncio
    async def test_http_exception_null_detail(self):
        app = Faster()

        @app.get("/empty")
        async def handler():
            raise HTTPException(status_code=204)

        send = MockSend()
        await app(_make_scope(path="/empty"), _receive, send)

        assert send.status == 204
        assert send.json == {"detail": None}


# ==============================
#  RequestValidationError format
# ==============================

class TestValidationErrorFormat:
    @pytest.mark.asyncio
    async def test_missing_path_param(self):
        from FasterAPI.params import Path as PathParam

        app = Faster()

        @app.get("/users/{user_id}")
        async def handler(user_id: str = PathParam()):
            return {"id": user_id}

        # Directly test that the route resolves and DI works
        send = MockSend()
        await app(_make_scope(path="/users/42"), _receive, send)
        assert send.status == 200

    @pytest.mark.asyncio
    async def test_invalid_struct_body(self):
        import msgspec as ms

        class Item(ms.Struct):
            name: str
            price: float

        app = Faster()

        @app.post("/items")
        async def handler(item: Item):
            return {"name": item.name}

        # Send invalid JSON body (missing price)
        body = b'{"name": "X"}'
        called = False

        async def receive():
            nonlocal called
            if not called:
                called = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        send = MockSend()
        await app(
            {**_make_scope(method="POST", path="/items")},
            receive,
            send,
        )

        assert send.status == 422
        detail = send.json["detail"]
        assert isinstance(detail, list)
        assert len(detail) >= 1
        assert "loc" in detail[0]
        assert "msg" in detail[0]
        assert "type" in detail[0]
        assert detail[0]["loc"] == ["body"]

    @pytest.mark.asyncio
    async def test_validation_error_direct(self):
        app = Faster()

        @app.get("/validate")
        async def handler():
            raise RequestValidationError([
                {"loc": ["query", "page"], "msg": "value is not a valid integer", "type": "type_error.integer"},
                {"loc": ["query", "limit"], "msg": "field required", "type": "value_error.missing"},
            ])

        send = MockSend()
        await app(_make_scope(path="/validate"), _receive, send)

        assert send.status == 422
        detail = send.json["detail"]
        assert len(detail) == 2
        assert detail[0] == {
            "loc": ["query", "page"],
            "msg": "value is not a valid integer",
            "type": "type_error.integer",
        }
        assert detail[1] == {
            "loc": ["query", "limit"],
            "msg": "field required",
            "type": "value_error.missing",
        }


# ==============================
#  Custom exception handlers
# ==============================

class TestCustomExceptionHandlers:
    @pytest.mark.asyncio
    async def test_custom_http_handler(self):
        app = Faster()

        async def custom_handler(request, exc):
            body = msgspec.json.encode({"error": "custom", "detail": exc.detail})
            return (
                exc.status_code,
                body,
                [(b"content-type", b"application/json")],
            )

        app.add_exception_handler(HTTPException, custom_handler)

        @app.get("/fail")
        async def handler():
            raise HTTPException(status_code=418, detail="I'm a teapot")

        send = MockSend()
        await app(_make_scope(path="/fail"), _receive, send)

        assert send.status == 418
        assert send.json == {"error": "custom", "detail": "I'm a teapot"}

    @pytest.mark.asyncio
    async def test_custom_validation_handler(self):
        app = Faster()

        async def custom_handler(request, exc):
            body = msgspec.json.encode({"errors": exc.errors, "count": len(exc.errors)})
            return (
                400,
                body,
                [(b"content-type", b"application/json")],
            )

        app.add_exception_handler(RequestValidationError, custom_handler)

        @app.get("/val")
        async def handler():
            raise RequestValidationError([{"loc": ["body"], "msg": "bad", "type": "error"}])

        send = MockSend()
        await app(_make_scope(path="/val"), _receive, send)

        assert send.status == 400
        data = send.json
        assert data["count"] == 1

    @pytest.mark.asyncio
    async def test_unhandled_exception_returns_500(self):
        app = Faster()

        @app.get("/crash")
        async def handler():
            raise RuntimeError("unexpected")

        send = MockSend()
        await app(_make_scope(path="/crash"), _receive, send)

        assert send.status == 500
        assert send.json == {"detail": "Internal Server Error"}

    @pytest.mark.asyncio
    async def test_generic_exception_handler(self):
        app = Faster()

        async def handle_runtime(request, exc):
            return {"error": str(exc)}

        app.add_exception_handler(RuntimeError, handle_runtime)

        @app.get("/crash")
        async def handler():
            raise RuntimeError("boom")

        send = MockSend()
        await app(_make_scope(path="/crash"), _receive, send)

        assert send.status == 200
        data = msgspec.json.decode(send.body)
        assert data == {"error": "boom"}
