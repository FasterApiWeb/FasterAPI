import asyncio

import msgspec
import pytest

from FasterAPI.dependencies import Depends, _resolve_handler
from FasterAPI.exceptions import HTTPException
from FasterAPI.params import Body, Cookie, Header, Path, Query
from FasterAPI.request import Request


# --------------- helpers ---------------

def _make_request(
    *,
    method: str = "GET",
    path: str = "/",
    headers: list[tuple[bytes, bytes]] | None = None,
    query_string: bytes = b"",
    path_params: dict | None = None,
    body: bytes = b"",
) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers or [],
        "query_string": query_string,
        "path_params": path_params or {},
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
#  Request injection
# ==============================

class TestRequestInjection:
    @pytest.mark.asyncio
    async def test_inject_request(self):
        async def handler(request: Request):
            return {"method": request.method}

        req = _make_request(method="POST")
        result = await _resolve_handler(handler, req, {})
        assert result == {"method": "POST"}


# ==============================
#  Path params
# ==============================

class TestPathParams:
    @pytest.mark.asyncio
    async def test_path_param(self):
        async def handler(user_id: str = Path()):
            return {"user_id": user_id}

        req = _make_request()
        result = await _resolve_handler(handler, req, {"user_id": "42"})
        assert result == {"user_id": "42"}

    @pytest.mark.asyncio
    async def test_path_param_missing_raises_422(self):
        async def handler(user_id: str = Path()):
            return user_id

        req = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            await _resolve_handler(handler, req, {})
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_path_param_with_default(self):
        async def handler(user_id: str = Path("default_id")):
            return {"user_id": user_id}

        req = _make_request()
        result = await _resolve_handler(handler, req, {})
        assert result == {"user_id": "default_id"}


# ==============================
#  Query params
# ==============================

class TestQueryParams:
    @pytest.mark.asyncio
    async def test_query_param(self):
        async def handler(q: str = Query()):
            return {"q": q}

        req = _make_request(query_string=b"q=search")
        result = await _resolve_handler(handler, req, {})
        assert result == {"q": "search"}

    @pytest.mark.asyncio
    async def test_query_param_default(self):
        async def handler(q: str = Query("default")):
            return {"q": q}

        req = _make_request()
        result = await _resolve_handler(handler, req, {})
        assert result == {"q": "default"}

    @pytest.mark.asyncio
    async def test_query_param_none_default(self):
        async def handler(q: str = Query()):
            return {"q": q}

        req = _make_request()
        result = await _resolve_handler(handler, req, {})
        assert result == {"q": None}

    @pytest.mark.asyncio
    async def test_query_param_alias(self):
        async def handler(q: str = Query(alias="search_query")):
            return {"q": q}

        req = _make_request(query_string=b"search_query=hello")
        result = await _resolve_handler(handler, req, {})
        assert result == {"q": "hello"}


# ==============================
#  Header params
# ==============================

class TestHeaderParams:
    @pytest.mark.asyncio
    async def test_header(self):
        async def handler(x_token: str = Header()):
            return {"token": x_token}

        req = _make_request(headers=[(b"x-token", b"abc123")])
        result = await _resolve_handler(handler, req, {})
        assert result == {"token": "abc123"}

    @pytest.mark.asyncio
    async def test_header_underscore_conversion(self):
        async def handler(content_type: str = Header()):
            return {"ct": content_type}

        req = _make_request(headers=[(b"content-type", b"text/plain")])
        result = await _resolve_handler(handler, req, {})
        assert result == {"ct": "text/plain"}

    @pytest.mark.asyncio
    async def test_header_alias(self):
        async def handler(token: str = Header(alias="Authorization")):
            return {"token": token}

        req = _make_request(headers=[(b"authorization", b"Bearer xyz")])
        result = await _resolve_handler(handler, req, {})
        assert result == {"token": "Bearer xyz"}

    @pytest.mark.asyncio
    async def test_header_default(self):
        async def handler(x_token: str = Header("fallback")):
            return {"token": x_token}

        req = _make_request()
        result = await _resolve_handler(handler, req, {})
        assert result == {"token": "fallback"}


# ==============================
#  Cookie params
# ==============================

class TestCookieParams:
    @pytest.mark.asyncio
    async def test_cookie(self):
        async def handler(session: str = Cookie()):
            return {"session": session}

        req = _make_request(headers=[(b"cookie", b"session=abc123")])
        result = await _resolve_handler(handler, req, {})
        assert result == {"session": "abc123"}

    @pytest.mark.asyncio
    async def test_cookie_default(self):
        async def handler(session: str = Cookie("none")):
            return {"session": session}

        req = _make_request()
        result = await _resolve_handler(handler, req, {})
        assert result == {"session": "none"}


# ==============================
#  Body / msgspec.Struct
# ==============================

class Item(msgspec.Struct):
    name: str
    price: float


class TestBodyParams:
    @pytest.mark.asyncio
    async def test_struct_decode(self):
        async def handler(item: Item):
            return {"name": item.name, "price": item.price}

        body = msgspec.json.encode({"name": "Widget", "price": 9.99})
        req = _make_request(method="POST", body=body)
        result = await _resolve_handler(handler, req, {})
        assert result == {"name": "Widget", "price": 9.99}

    @pytest.mark.asyncio
    async def test_struct_invalid_raises_422(self):
        async def handler(item: Item):
            return item

        req = _make_request(method="POST", body=b'{"name": "X"}')
        with pytest.raises(HTTPException) as exc_info:
            await _resolve_handler(handler, req, {})
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_body_marker(self):
        async def handler(data: dict = Body()):
            return data

        body = msgspec.json.encode({"key": "value"})
        req = _make_request(method="POST", body=body)
        result = await _resolve_handler(handler, req, {})
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_body_marker_default_on_failure(self):
        async def handler(data: dict = Body({"fallback": True})):
            return data

        req = _make_request(method="POST", body=b"not json")
        result = await _resolve_handler(handler, req, {})
        assert result == {"fallback": True}


# ==============================
#  Depends()
# ==============================

class TestDepends:
    @pytest.mark.asyncio
    async def test_simple_dependency(self):
        async def get_db():
            return {"db": "connected"}

        async def handler(db=Depends(get_db)):
            return db

        req = _make_request()
        result = await _resolve_handler(handler, req, {})
        assert result == {"db": "connected"}

    @pytest.mark.asyncio
    async def test_dependency_with_request(self):
        async def get_user(request: Request):
            return {"user": request.headers.get("x-user", "anon")}

        async def handler(user=Depends(get_user)):
            return user

        req = _make_request(headers=[(b"x-user", b"alice")])
        result = await _resolve_handler(handler, req, {})
        assert result == {"user": "alice"}

    @pytest.mark.asyncio
    async def test_nested_dependencies(self):
        async def get_config():
            return {"env": "test"}

        async def get_db(config=Depends(get_config)):
            return {"db": "ok", **config}

        async def handler(db=Depends(get_db)):
            return db

        req = _make_request()
        result = await _resolve_handler(handler, req, {})
        assert result == {"db": "ok", "env": "test"}

    @pytest.mark.asyncio
    async def test_dependency_caching(self):
        call_count = 0

        async def expensive():
            nonlocal call_count
            call_count += 1
            return call_count

        async def dep_a(val=Depends(expensive)):
            return val

        async def dep_b(val=Depends(expensive)):
            return val

        async def handler(a=Depends(dep_a), b=Depends(dep_b)):
            return {"a": a, "b": b}

        req = _make_request()
        result = await _resolve_handler(handler, req, {})
        # expensive() should only be called once due to caching
        assert result["a"] == 1
        assert result["b"] == 1
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_dependency_no_cache(self):
        call_count = 0

        async def counter():
            nonlocal call_count
            call_count += 1
            return call_count

        async def handler(
            a=Depends(counter, use_cache=False),
            b=Depends(counter, use_cache=False),
        ):
            return {"a": a, "b": b}

        req = _make_request()
        result = await _resolve_handler(handler, req, {})
        assert result["a"] == 1
        assert result["b"] == 2
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_sync_dependency(self):
        def get_version():
            return "1.0"

        async def handler(version=Depends(get_version)):
            return {"version": version}

        req = _make_request()
        result = await _resolve_handler(handler, req, {})
        assert result == {"version": "1.0"}


# ==============================
#  Sync handlers
# ==============================

class TestSyncHandlers:
    @pytest.mark.asyncio
    async def test_sync_handler(self):
        def handler(q: str = Query("hi")):
            return {"q": q}

        req = _make_request()
        result = await _resolve_handler(handler, req, {})
        assert result == {"q": "hi"}


# ==============================
#  Combined params
# ==============================

class TestCombinedParams:
    @pytest.mark.asyncio
    async def test_multiple_param_types(self):
        async def handler(
            user_id: str = Path(),
            q: str = Query("default"),
            x_token: str = Header("none"),
        ):
            return {"user_id": user_id, "q": q, "token": x_token}

        req = _make_request(
            query_string=b"q=search",
            headers=[(b"x-token", b"secret")],
        )
        result = await _resolve_handler(handler, req, {"user_id": "7"})
        assert result == {"user_id": "7", "q": "search", "token": "secret"}

    @pytest.mark.asyncio
    async def test_unannotated_falls_back_to_path_params(self):
        async def handler(id):
            return {"id": id}

        req = _make_request()
        result = await _resolve_handler(handler, req, {"id": "99"})
        assert result == {"id": "99"}
