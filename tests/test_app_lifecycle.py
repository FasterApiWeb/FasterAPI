"""Lifespan, errors, and middleware wiring."""

import pytest

from FasterAPI.app import Faster
from FasterAPI.exceptions import HTTPException


@pytest.mark.asyncio
async def test_lifespan_startup_shutdown():
    app = Faster(openapi_url=None, docs_url=None, redoc_url=None)
    log: list[str] = []

    @app.on_startup
    def up():
        log.append("up")

    @app.on_shutdown
    async def down():
        log.append("down")

    sent: list[dict] = []
    messages = [
        {"type": "lifespan.startup"},
        {"type": "lifespan.shutdown"},
    ]
    idx = [0]

    async def receive():
        m = messages[idx[0]]
        idx[0] += 1
        return m

    async def send(msg: dict) -> None:
        sent.append(msg)

    scope = {"type": "lifespan"}
    await app(scope, receive, send)

    assert log == ["up", "down"]
    assert any(x.get("type") == "lifespan.startup.complete" for x in sent)
    assert any(x.get("type") == "lifespan.shutdown.complete" for x in sent)


@pytest.mark.asyncio
async def test_404():
    app = Faster(openapi_url=None, docs_url=None, redoc_url=None)
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg: dict) -> None:
        sent.append(msg)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/nope",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
    }
    await app(scope, receive, send)
    assert sent[0]["status"] == 404


@pytest.mark.asyncio
async def test_custom_exception_handler():
    app = Faster(openapi_url=None, docs_url=None, redoc_url=None)

    class Boom(Exception):
        pass

    @app.get("/x")
    async def x():
        raise Boom()

    def handle(request, exc: Boom):
        from FasterAPI.response import PlainTextResponse
        return PlainTextResponse("handled", 418)

    app.add_exception_handler(Boom, handle)

    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg: dict) -> None:
        sent.append(msg)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
    }
    await app(scope, receive, send)
    assert sent[0]["status"] == 418
    assert b"handled" in sent[1]["body"]


@pytest.mark.asyncio
async def test_http_exception_handler_path():
    app = Faster(openapi_url=None, docs_url=None, redoc_url=None)

    @app.get("/e")
    async def e():
        raise HTTPException(403, detail="forbidden")

    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg: dict) -> None:
        sent.append(msg)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/e",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
    }
    await app(scope, receive, send)
    assert sent[0]["status"] == 403


@pytest.mark.asyncio
async def test_middleware_chain_builds_once():
    from FasterAPI.middleware import BaseHTTPMiddleware

    class MW(BaseHTTPMiddleware):
        async def dispatch(self, scope, receive, send):
            await self.app(scope, receive, send)

    app = Faster(openapi_url=None, docs_url=None, redoc_url=None)
    app.add_middleware(MW)

    @app.get("/z")
    async def z():
        return {"z": 1}

    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg: dict) -> None:
        sent.append(msg)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/z",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
    }
    await app(scope, receive, send)
    assert app._middleware_app is not None
    assert sent[0]["status"] == 200
