import inspect

import pytest
from FasterAPI.params import (
    MISSING,
    Body,
    Cookie,
    File,
    Form,
    Header,
    Path,
    Query,
)
from FasterAPI.request import Request

# --------------- helpers ---------------


def _make_scope(
    *,
    method: str = "GET",
    path: str = "/",
    headers: list[tuple[bytes, bytes]] | None = None,
    query_string: bytes = b"",
    path_params: dict | None = None,
    client: tuple[str, int] | None = None,
) -> dict:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers or [],
        "query_string": query_string,
        "path_params": path_params or {},
        "client": client,
    }


async def _receive_body(body: bytes = b""):
    called = False

    async def receive():
        nonlocal called
        if not called:
            called = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    return receive


# ==============================
#  Request tests
# ==============================


class TestRequestBasics:
    def test_method_and_path(self):
        scope = _make_scope(method="POST", path="/users")
        req = Request(scope, None)
        assert req.method == "POST"
        assert req.path == "/users"

    def test_headers_lowercase(self):
        scope = _make_scope(
            headers=[
                (b"Content-Type", b"application/json"),
                (b"X-Custom", b"value"),
            ]
        )
        req = Request(scope, None)
        assert req.headers["content-type"] == "application/json"
        assert req.headers["x-custom"] == "value"

    def test_path_params(self):
        scope = _make_scope(path_params={"id": "42", "slug": "hello"})
        req = Request(scope, None)
        assert req.path_params == {"id": "42", "slug": "hello"}

    def test_query_params_single(self):
        scope = _make_scope(query_string=b"page=1&limit=10")
        req = Request(scope, None)
        assert req.query_params == {"page": "1", "limit": "10"}

    def test_query_params_empty(self):
        scope = _make_scope(query_string=b"")
        req = Request(scope, None)
        assert req.query_params == {}


class TestRequestClient:
    def test_client_present(self):
        scope = _make_scope(client=("127.0.0.1", 8000))
        req = Request(scope, None)
        assert req.client == ("127.0.0.1", 8000)

    def test_client_absent(self):
        scope = _make_scope()
        req = Request(scope, None)
        assert req.client is None


class TestRequestCookies:
    def test_cookies_parsed(self):
        scope = _make_scope(
            headers=[
                (b"cookie", b"session=abc123; theme=dark"),
            ]
        )
        req = Request(scope, None)
        assert req.cookies == {"session": "abc123", "theme": "dark"}

    def test_no_cookies(self):
        scope = _make_scope()
        req = Request(scope, None)
        assert req.cookies == {}


class TestRequestContentType:
    def test_content_type(self):
        scope = _make_scope(
            headers=[
                (b"content-type", b"application/json"),
            ]
        )
        req = Request(scope, None)
        assert req.content_type == "application/json"

    def test_no_content_type(self):
        scope = _make_scope()
        req = Request(scope, None)
        assert req.content_type is None


class TestRequestJson:
    @pytest.mark.asyncio
    async def test_json_decode(self):
        body = b'{"name": "alice", "age": 30}'
        receive = await _receive_body(body)
        scope = _make_scope(method="POST")
        req = Request(scope, receive)
        data = await req.json()
        assert data == {"name": "alice", "age": 30}

    @pytest.mark.asyncio
    async def test_json_body_cached(self):
        body = b'{"x": 1}'
        receive = await _receive_body(body)
        scope = _make_scope(method="POST")
        req = Request(scope, receive)
        d1 = await req.json()
        d2 = await req.json()
        assert d1 == d2


class TestRequestForm:
    @pytest.mark.asyncio
    async def test_urlencoded_form(self):
        body = b"username=alice&password=secret"
        receive = await _receive_body(body)
        scope = _make_scope(
            method="POST",
            headers=[(b"content-type", b"application/x-www-form-urlencoded")],
        )
        req = Request(scope, receive)
        data = await req.form()
        assert data == {"username": "alice", "password": "secret"}

    @pytest.mark.asyncio
    async def test_multipart_form(self):
        boundary = "----boundary"
        body = (
            b"------boundary\r\n"
            b'Content-Disposition: form-data; name="field1"\r\n\r\n'
            b"value1\r\n"
            b"------boundary\r\n"
            b'Content-Disposition: form-data; name="field2"\r\n\r\n'
            b"value2\r\n"
            b"------boundary--\r\n"
        )
        receive = await _receive_body(body)
        scope = _make_scope(
            method="POST",
            headers=[(b"content-type", f"multipart/form-data; boundary={boundary}".encode())],
        )
        req = Request(scope, receive)
        data = await req.form()
        assert data["field1"] == "value1"
        assert data["field2"] == "value2"


# ==============================
#  Param descriptor tests
# ==============================


class TestPathParam:
    def test_defaults(self):
        p = Path()
        assert p.default is MISSING
        assert p.description == ""

    def test_custom(self):
        p = Path(description="User ID")
        assert p.default is MISSING
        assert p.description == "User ID"

    def test_repr(self):
        assert repr(Path()) == "Path()"
        assert repr(Path("x")) == "Path(default='x')"


class TestQueryParam:
    def test_defaults(self):
        q = Query()
        assert q.default is None
        assert q.alias is None

    def test_with_default(self):
        q = Query("all", alias="filter_type")
        assert q.default == "all"
        assert q.alias == "filter_type"

    def test_repr(self):
        assert repr(Query()) == "Query(default=None)"


class TestBodyParam:
    def test_defaults(self):
        b = Body()
        assert b.default is MISSING
        assert b.embed is False

    def test_with_embed(self):
        b = Body(embed=True)
        assert b.embed is True

    def test_repr(self):
        assert repr(Body()) == "Body()"
        assert repr(Body(None)) == "Body(default=None)"


class TestHeaderParam:
    def test_defaults(self):
        h = Header()
        assert h.default is None
        assert h.convert_underscores is True

    def test_custom(self):
        h = Header("val", alias="X-Custom", convert_underscores=False)
        assert h.default == "val"
        assert h.alias == "X-Custom"
        assert h.convert_underscores is False


class TestCookieParam:
    def test_defaults(self):
        c = Cookie()
        assert c.default is None

    def test_custom(self):
        c = Cookie("session_val")
        assert c.default == "session_val"


class TestFileParam:
    def test_defaults(self):
        f = File()
        assert f.description == ""
        assert repr(f) == "File()"


class TestFormParam:
    def test_defaults(self):
        f = Form()
        assert f.default is MISSING

    def test_repr(self):
        assert repr(Form()) == "Form()"
        assert repr(Form("x")) == "Form(default='x')"


# ==============================
#  Signature-level usage
# ==============================


class TestSignatureUsage:
    def test_params_as_defaults_in_signature(self):
        """Verify param descriptors work as default values in function signatures."""

        async def get_user(
            user_id: str = Path(),
            q: str = Query(None),
            x_token: str = Header(alias="X-Token"),
        ):
            pass

        sig = inspect.signature(get_user)
        params = sig.parameters

        assert isinstance(params["user_id"].default, Path)
        assert isinstance(params["q"].default, Query)
        assert params["q"].default.default is None
        assert isinstance(params["x_token"].default, Header)
        assert params["x_token"].default.alias == "X-Token"

    def test_body_in_signature(self):
        async def create_item(
            item: dict = Body(description="The item to create"),
            tag: str = Query("default"),
        ):
            pass

        sig = inspect.signature(create_item)
        assert isinstance(sig.parameters["item"].default, Body)
        assert sig.parameters["item"].default.description == "The item to create"
        assert sig.parameters["tag"].default.default == "default"
