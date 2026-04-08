import gzip

import msgspec
import pytest

from faster.app import Faster
from faster.middleware import (
    CORSMiddleware,
    GZipMiddleware,
    HTTPSRedirectMiddleware,
    TrustedHostMiddleware,
)


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

    def header(self, name: str) -> str | None:
        for k, v in self.messages[0]["headers"]:
            if k == name.encode("latin-1"):
                return v.decode("latin-1")
        return None

    def all_headers(self, name: str) -> list[str]:
        results = []
        for k, v in self.messages[0]["headers"]:
            if k == name.encode("latin-1"):
                results.append(v.decode("latin-1"))
        return results


def _make_scope(
    method: str = "GET",
    path: str = "/test",
    headers: list[tuple[bytes, bytes]] | None = None,
    scheme: str = "http",
) -> dict:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers or [],
        "query_string": b"",
        "scheme": scheme,
    }


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _make_app() -> Faster:
    app = Faster(openapi_url=None)

    @app.get("/test")
    async def test_handler():
        return {"message": "ok"}

    return app


def _make_big_app() -> Faster:
    app = Faster(openapi_url=None)

    @app.get("/big")
    async def big_handler():
        return {"data": "x" * 2000}

    @app.get("/small")
    async def small_handler():
        return {"data": "small"}

    return app


# ==============================
#  CORS Middleware
# ==============================

class TestCORSBasic:
    @pytest.mark.asyncio
    async def test_cors_allow_all_origins(self):
        app = _make_app()
        app.add_middleware(CORSMiddleware, allow_origins=["*"])

        send = MockSend()
        scope = _make_scope(headers=[(b"origin", b"http://example.com")])
        await app(scope, _receive, send)

        assert send.status == 200
        assert send.header("access-control-allow-origin") == "*"

    @pytest.mark.asyncio
    async def test_cors_specific_origin(self):
        app = _make_app()
        app.add_middleware(CORSMiddleware, allow_origins=["http://example.com"])

        send = MockSend()
        scope = _make_scope(headers=[(b"origin", b"http://example.com")])
        await app(scope, _receive, send)

        assert send.header("access-control-allow-origin") == "http://example.com"

    @pytest.mark.asyncio
    async def test_cors_disallowed_origin(self):
        app = _make_app()
        app.add_middleware(CORSMiddleware, allow_origins=["http://allowed.com"])

        send = MockSend()
        scope = _make_scope(headers=[(b"origin", b"http://evil.com")])
        await app(scope, _receive, send)

        assert send.header("access-control-allow-origin") is None

    @pytest.mark.asyncio
    async def test_cors_no_origin_header(self):
        app = _make_app()
        app.add_middleware(CORSMiddleware, allow_origins=["*"])

        send = MockSend()
        scope = _make_scope()
        await app(scope, _receive, send)

        # No origin in request → no CORS headers
        assert send.header("access-control-allow-origin") is None


class TestCORSPreflight:
    @pytest.mark.asyncio
    async def test_preflight_request(self):
        app = _make_app()
        app.add_middleware(CORSMiddleware, allow_origins=["*"], max_age=3600)

        send = MockSend()
        scope = _make_scope(
            method="OPTIONS",
            headers=[
                (b"origin", b"http://example.com"),
                (b"access-control-request-method", b"POST"),
                (b"access-control-request-headers", b"Content-Type"),
            ],
        )
        await app(scope, _receive, send)

        assert send.status == 200
        assert send.header("access-control-allow-origin") == "*"
        assert send.header("access-control-allow-methods") == "POST"
        assert send.header("access-control-allow-headers") == "Content-Type"
        assert send.header("access-control-max-age") == "3600"

    @pytest.mark.asyncio
    async def test_preflight_specific_methods(self):
        app = _make_app()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["GET", "POST"],
            allow_headers=["X-Custom"],
        )

        send = MockSend()
        scope = _make_scope(
            method="OPTIONS",
            headers=[
                (b"origin", b"http://example.com"),
                (b"access-control-request-method", b"POST"),
            ],
        )
        await app(scope, _receive, send)

        assert "GET" in send.header("access-control-allow-methods")
        assert "POST" in send.header("access-control-allow-methods")
        assert send.header("access-control-allow-headers") == "X-Custom"


class TestCORSCredentials:
    @pytest.mark.asyncio
    async def test_credentials(self):
        app = _make_app()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://example.com"],
            allow_credentials=True,
        )

        send = MockSend()
        scope = _make_scope(headers=[(b"origin", b"http://example.com")])
        await app(scope, _receive, send)

        assert send.header("access-control-allow-credentials") == "true"
        # With credentials, origin should be specific, not *
        assert send.header("access-control-allow-origin") == "http://example.com"


# ==============================
#  GZip Middleware
# ==============================

class TestGZipMiddleware:
    @pytest.mark.asyncio
    async def test_gzip_compresses_large_response(self):
        app = _make_big_app()
        app.add_middleware(GZipMiddleware, minimum_size=500)

        send = MockSend()
        scope = _make_scope(
            path="/big",
            headers=[(b"accept-encoding", b"gzip, deflate")],
        )
        await app(scope, _receive, send)

        assert send.status == 200
        assert send.header("content-encoding") == "gzip"
        # Verify it's actually gzip-compressed
        decompressed = gzip.decompress(send.body)
        data = msgspec.json.decode(decompressed)
        assert len(data["data"]) == 2000

    @pytest.mark.asyncio
    async def test_gzip_skips_small_response(self):
        app = _make_big_app()
        app.add_middleware(GZipMiddleware, minimum_size=500)

        send = MockSend()
        scope = _make_scope(
            path="/small",
            headers=[(b"accept-encoding", b"gzip, deflate")],
        )
        await app(scope, _receive, send)

        assert send.header("content-encoding") is None
        data = msgspec.json.decode(send.body)
        assert data["data"] == "small"

    @pytest.mark.asyncio
    async def test_gzip_skips_without_accept_encoding(self):
        app = _make_big_app()
        app.add_middleware(GZipMiddleware, minimum_size=500)

        send = MockSend()
        scope = _make_scope(path="/big")
        await app(scope, _receive, send)

        assert send.header("content-encoding") is None

    @pytest.mark.asyncio
    async def test_gzip_vary_header(self):
        app = _make_big_app()
        app.add_middleware(GZipMiddleware, minimum_size=500)

        send = MockSend()
        scope = _make_scope(
            path="/big",
            headers=[(b"accept-encoding", b"gzip")],
        )
        await app(scope, _receive, send)

        assert "Accept-Encoding" in send.all_headers("vary")


# ==============================
#  TrustedHost Middleware
# ==============================

class TestTrustedHostMiddleware:
    @pytest.mark.asyncio
    async def test_allowed_host(self):
        app = _make_app()
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["example.com"])

        send = MockSend()
        scope = _make_scope(headers=[(b"host", b"example.com")])
        await app(scope, _receive, send)

        assert send.status == 200

    @pytest.mark.asyncio
    async def test_disallowed_host(self):
        app = _make_app()
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["example.com"])

        send = MockSend()
        scope = _make_scope(headers=[(b"host", b"evil.com")])
        await app(scope, _receive, send)

        assert send.status == 400

    @pytest.mark.asyncio
    async def test_wildcard_allows_all(self):
        app = _make_app()
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

        send = MockSend()
        scope = _make_scope(headers=[(b"host", b"anything.com")])
        await app(scope, _receive, send)

        assert send.status == 200

    @pytest.mark.asyncio
    async def test_host_with_port(self):
        app = _make_app()
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["example.com"])

        send = MockSend()
        scope = _make_scope(headers=[(b"host", b"example.com:8000")])
        await app(scope, _receive, send)

        assert send.status == 200


# ==============================
#  HTTPS Redirect Middleware
# ==============================

class TestHTTPSRedirectMiddleware:
    @pytest.mark.asyncio
    async def test_http_redirects(self):
        app = _make_app()
        app.add_middleware(HTTPSRedirectMiddleware)

        send = MockSend()
        scope = _make_scope(
            scheme="http",
            headers=[(b"host", b"example.com")],
        )
        await app(scope, _receive, send)

        assert send.status == 301
        assert send.header("location") == "https://example.com/test"

    @pytest.mark.asyncio
    async def test_https_passes_through(self):
        app = _make_app()
        app.add_middleware(HTTPSRedirectMiddleware)

        send = MockSend()
        scope = _make_scope(scheme="https")
        await app(scope, _receive, send)

        assert send.status == 200


# ==============================
#  Middleware chain
# ==============================

class TestMiddlewareChain:
    @pytest.mark.asyncio
    async def test_chain_is_cached(self):
        app = _make_app()
        app.add_middleware(CORSMiddleware, allow_origins=["*"])

        send1 = MockSend()
        send2 = MockSend()
        scope = _make_scope(headers=[(b"origin", b"http://a.com")])

        await app(scope, _receive, send1)
        await app(scope, _receive, send2)

        # Should be the same middleware chain object
        assert app._middleware_app is not None
        assert send1.header("access-control-allow-origin") == "*"
        assert send2.header("access-control-allow-origin") == "*"

    @pytest.mark.asyncio
    async def test_multiple_middleware(self):
        app = _make_app()
        app.add_middleware(CORSMiddleware, allow_origins=["*"])
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["example.com"])

        send = MockSend()
        scope = _make_scope(headers=[
            (b"origin", b"http://example.com"),
            (b"host", b"example.com"),
        ])
        await app(scope, _receive, send)

        assert send.status == 200
        assert send.header("access-control-allow-origin") == "*"
