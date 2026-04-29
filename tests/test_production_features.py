"""Tests for production-hardening features (v0.2.0 roadmap)."""

from __future__ import annotations

import pytest
from FasterAPI import Faster, Request
from FasterAPI.asgi_compat import get_server_host, http_version, is_http2
from FasterAPI.log_config import configure_structlog
from FasterAPI.production import DatabasePoolMiddleware, RateLimitMiddleware, RequestIDMiddleware
from FasterAPI.testclient import TestClient


@pytest.fixture
def simple_app():
    app = Faster()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app


def test_database_pool_middleware_state(simple_app):
    pool = object()
    simple_app.add_middleware(DatabasePoolMiddleware, pool=pool, state_key="engine")

    @simple_app.get("/db")
    async def db_route(request: Request):
        assert request.state["engine"] is pool
        return {"via": "pool"}

    client = TestClient(simple_app)
    r = client.get("/db")
    assert r.status_code == 200


def test_request_id_middleware_header(simple_app):
    simple_app.add_middleware(RequestIDMiddleware)

    @simple_app.get("/rid")
    async def rid(request: Request):
        assert "request_id" in request.state
        return {"id": request.state["request_id"]}

    client = TestClient(simple_app)
    r = client.get("/rid")
    assert r.status_code == 200
    assert "x-request-id" in r.headers
    assert len(r.json()["id"]) >= 8


def test_request_id_propagate(simple_app):
    simple_app.add_middleware(RequestIDMiddleware)

    client = TestClient(simple_app)
    r = client.get("/ping", headers={"X-Request-ID": "upstream-abc"})
    assert r.headers.get("x-request-id") == "upstream-abc"


def test_rate_limit_middleware_429():
    app = Faster()

    @app.get("/limited")
    async def limited():
        return {"n": 1}

    app.add_middleware(RateLimitMiddleware, requests_per_minute=2, window_seconds=60.0)

    client = TestClient(app)
    assert client.get("/limited").status_code == 200
    assert client.get("/limited").status_code == 200
    r3 = client.get("/limited")
    assert r3.status_code == 429


def test_max_body_size_413():
    app = Faster(max_body_size=10)

    @app.post("/big")
    async def big(request: Request):
        await request._read_body()
        return {"ok": True}

    client = TestClient(app)
    r = client.post("/big", content=b"x" * 50)
    assert r.status_code == 413


def test_stream_accumulates_body():
    app = Faster()

    @app.post("/echo")
    async def echo(request: Request):
        chunks = []
        async for c in request.stream():
            chunks.append(c)
        return {"joined": b"".join(chunks).decode()}

    client = TestClient(app)
    r = client.post("/echo", content=b"hello")
    assert r.status_code == 200
    assert r.json()["joined"] == "hello"


def test_asgi_compat_helpers():
    scope = {
        "headers": [(b"host", b"example.org:443")],
        "http_version": "2",
    }
    assert get_server_host(scope) == "example.org"
    assert is_http2(scope)
    assert http_version(scope) == "2"


def test_configure_structlog_smoke():
    configure_structlog(json_format=False, log_level="INFO")
    import structlog

    log = structlog.get_logger()
    log.info("smoke", feature="test")
