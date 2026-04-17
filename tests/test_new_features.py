"""Tests for the newly added features:
  - Security utilities (OAuth2, HTTPBasic, APIKey*)
  - Lifespan context manager
  - response_model / response_model_include / response_model_exclude
  - Annotated[T, Depends(...)] — PEP 593 style
  - Sub-application mounting (mount())
  - Server-Sent Events (EventSourceResponse)
  - ORJSONResponse / UJSONResponse aliases
  - datetime / UUID / Decimal serialization
  - Multiple response declarations (responses={...})
  - APIRouter dependencies
  - Dataclass support
  - Enum path parameters in OpenAPI
  - openapi_tags / terms_of_service / contact / license_info
"""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import enum
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

import msgspec
import pytest

from FasterAPI import (
    Depends,
    EventSourceResponse,
    Faster,
    FasterRouter,
    HTTPBasic,
    HTTPBasicCredentials,
    JSONResponse,
    ORJSONResponse,
    Request,
    UJSONResponse,
    APIKeyHeader,
    APIKeyQuery,
    APIKeyCookie,
    OAuth2PasswordBearer,
    SecurityScopes,
    StaticFiles,
)
from FasterAPI.testclient import TestClient


# ---------------------------------------------------------------------------
#  Security — OAuth2PasswordBearer
# ---------------------------------------------------------------------------


def test_oauth2_password_bearer_valid():
    oauth2 = OAuth2PasswordBearer(tokenUrl="/token")
    app = Faster()

    @app.get("/me")
    async def me(token: str = Depends(oauth2)):
        return {"token": token}

    client = TestClient(app)
    resp = client.get("/me", headers={"Authorization": "Bearer mytoken123"})
    assert resp.status_code == 200
    assert resp.json() == {"token": "mytoken123"}


def test_oauth2_password_bearer_missing():
    oauth2 = OAuth2PasswordBearer(tokenUrl="/token")
    app = Faster()

    @app.get("/me")
    async def me(token: str = Depends(oauth2)):
        return {"token": token}

    client = TestClient(app)
    resp = client.get("/me")
    assert resp.status_code == 401


def test_oauth2_password_bearer_no_auto_error():
    oauth2 = OAuth2PasswordBearer(tokenUrl="/token", auto_error=False)
    app = Faster()

    @app.get("/me")
    async def me(token: str | None = Depends(oauth2)):
        return {"token": token}

    client = TestClient(app)
    resp = client.get("/me")
    assert resp.status_code == 200
    assert resp.json() == {"token": None}


# ---------------------------------------------------------------------------
#  Security — HTTPBasic
# ---------------------------------------------------------------------------


def test_http_basic_valid():
    import base64

    http_basic = HTTPBasic()
    app = Faster()

    @app.get("/protected")
    async def protected(creds: HTTPBasicCredentials = Depends(http_basic)):
        return {"username": creds.username}

    client = TestClient(app)
    encoded = base64.b64encode(b"alice:secret").decode()
    resp = client.get("/protected", headers={"Authorization": f"Basic {encoded}"})
    assert resp.status_code == 200
    assert resp.json() == {"username": "alice"}


def test_http_basic_missing():
    http_basic = HTTPBasic()
    app = Faster()

    @app.get("/protected")
    async def protected(creds: HTTPBasicCredentials = Depends(http_basic)):
        return {"username": creds.username}

    client = TestClient(app)
    resp = client.get("/protected")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
#  Security — API Key variants
# ---------------------------------------------------------------------------


def test_api_key_header():
    api_key = APIKeyHeader(name="X-API-Key")
    app = Faster()

    @app.get("/secure")
    async def secure(key: str = Depends(api_key)):
        return {"key": key}

    client = TestClient(app)
    resp = client.get("/secure", headers={"X-API-Key": "secret123"})
    assert resp.status_code == 200
    assert resp.json() == {"key": "secret123"}


def test_api_key_query():
    api_key = APIKeyQuery(name="api_key")
    app = Faster()

    @app.get("/secure")
    async def secure(key: str = Depends(api_key)):
        return {"key": key}

    client = TestClient(app)
    resp = client.get("/secure?api_key=mykey")
    assert resp.status_code == 200
    assert resp.json() == {"key": "mykey"}


def test_api_key_cookie():
    api_key = APIKeyCookie(name="session")
    app = Faster()

    @app.get("/secure")
    async def secure(key: str = Depends(api_key)):
        return {"key": key}

    client = TestClient(app)
    resp = client.get("/secure", cookies={"session": "cookietoken"})
    assert resp.status_code == 200
    assert resp.json() == {"key": "cookietoken"}


# ---------------------------------------------------------------------------
#  SecurityScopes
# ---------------------------------------------------------------------------


def test_security_scopes():
    scopes = SecurityScopes(["read:users", "write:users"])
    assert scopes.scopes == ["read:users", "write:users"]
    assert scopes.scope_str == "read:users write:users"


# ---------------------------------------------------------------------------
#  Lifespan context manager
# ---------------------------------------------------------------------------


def test_lifespan_context_manager():
    state: list[str] = []

    @asynccontextmanager
    async def lifespan(app: Faster):
        state.append("startup")
        yield
        state.append("shutdown")

    app = Faster(lifespan=lifespan)

    @app.get("/")
    async def root():
        return {"state": state}

    with TestClient(app):
        pass

    assert state == ["startup", "shutdown"]


def test_lifespan_and_route():
    db: dict[str, str] = {}

    @asynccontextmanager
    async def lifespan(app: Faster):
        db["initialized"] = "true"
        yield
        db.clear()

    app = Faster(lifespan=lifespan)

    @app.get("/db")
    async def check():
        return {"initialized": db.get("initialized")}

    with TestClient(app) as client:
        resp = client.get("/db")
        assert resp.json() == {"initialized": "true"}


# ---------------------------------------------------------------------------
#  response_model filtering
# ---------------------------------------------------------------------------


class UserFull(msgspec.Struct):
    id: int
    name: str
    password: str


class UserPublic(msgspec.Struct):
    id: int
    name: str


def test_response_model_filters_fields():
    app = Faster()

    @app.get("/user", response_model=UserPublic)
    async def get_user():
        return UserFull(id=1, name="Alice", password="secret")

    client = TestClient(app)
    resp = client.get("/user")
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "name" in data
    assert "password" not in data


def test_response_model_include():
    app = Faster()

    @app.get("/user", response_model=UserFull, response_model_include={"id", "name"})
    async def get_user():
        return UserFull(id=1, name="Alice", password="secret")

    client = TestClient(app)
    resp = client.get("/user")
    data = resp.json()
    assert "password" not in data
    assert data["name"] == "Alice"


def test_response_model_exclude():
    app = Faster()

    @app.get("/user", response_model=UserFull, response_model_exclude={"password"})
    async def get_user():
        return UserFull(id=1, name="Alice", password="secret")

    client = TestClient(app)
    resp = client.get("/user")
    data = resp.json()
    assert "password" not in data
    assert data["id"] == 1


# ---------------------------------------------------------------------------
#  Annotated PEP 593 style dependencies
# ---------------------------------------------------------------------------


def get_token_dep(request: Request) -> str:
    return request.headers.get("x-token", "none")


def test_annotated_depends():
    app = Faster()

    @app.get("/annotated")
    async def handler(token: Annotated[str, Depends(get_token_dep)]):
        return {"token": token}

    client = TestClient(app)
    resp = client.get("/annotated", headers={"X-Token": "hello"})
    assert resp.status_code == 200
    assert resp.json() == {"token": "hello"}


# ---------------------------------------------------------------------------
#  Sub-application mounting
# ---------------------------------------------------------------------------


def test_mount_sub_app():
    sub = Faster()

    @sub.get("/hello")
    async def sub_hello():
        return {"from": "sub"}

    app = Faster()
    app.mount("/sub", sub)

    client = TestClient(app)
    resp = client.get("/sub/hello")
    assert resp.status_code == 200
    assert resp.json() == {"from": "sub"}


# ---------------------------------------------------------------------------
#  Server-Sent Events
# ---------------------------------------------------------------------------


def test_event_source_response_sync():
    def generator():
        yield {"data": "hello"}
        yield {"event": "update", "data": "world", "id": "1"}

    app = Faster()

    @app.get("/stream")
    async def stream():
        return EventSourceResponse(generator())

    client = TestClient(app)
    resp = client.get("/stream")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "data: hello" in body
    assert "event: update" in body


def test_event_source_response_format():
    from FasterAPI.response import EventSourceResponse as ESR

    sse = ESR.__new__(ESR)
    chunk = sse._format_event({"event": "msg", "data": "hi", "id": "42"})
    text = chunk.decode()
    assert "event: msg" in text
    assert "data: hi" in text
    assert "id: 42" in text


# ---------------------------------------------------------------------------
#  ORJSONResponse / UJSONResponse aliases
# ---------------------------------------------------------------------------


def test_orjson_response_alias():
    assert ORJSONResponse is JSONResponse


def test_ujson_response_alias():
    assert UJSONResponse is JSONResponse


# ---------------------------------------------------------------------------
#  datetime / UUID / Decimal serialization
# ---------------------------------------------------------------------------


def test_datetime_serialization():
    app = Faster()
    now = datetime.datetime(2024, 1, 15, 10, 30, 0)

    @app.get("/dt")
    async def get_dt():
        return {"dt": now}

    client = TestClient(app)
    resp = client.get("/dt")
    assert resp.status_code == 200
    assert "2024-01-15" in resp.json()["dt"]


def test_uuid_serialization():
    app = Faster()
    uid = uuid.UUID("12345678-1234-5678-1234-567812345678")

    @app.get("/uid")
    async def get_uid():
        return {"uid": uid}

    client = TestClient(app)
    resp = client.get("/uid")
    assert resp.status_code == 200
    assert resp.json()["uid"] == str(uid)


def test_decimal_serialization():
    app = Faster()

    @app.get("/dec")
    async def get_dec():
        return {"value": decimal.Decimal("3.14159")}

    client = TestClient(app)
    resp = client.get("/dec")
    assert resp.status_code == 200
    assert resp.json()["value"] == "3.14159"


# ---------------------------------------------------------------------------
#  Multiple response declarations (responses={...})
# ---------------------------------------------------------------------------


def test_multiple_responses_in_openapi():
    app = Faster()

    @app.get(
        "/items/{id}",
        responses={404: {"description": "Item not found"}, 403: {"description": "Forbidden"}},
    )
    async def get_item(id: int):
        return {"id": id}

    from FasterAPI.openapi.generator import generate_openapi

    spec = generate_openapi(app, title="Test", version="0.1")
    path = spec["paths"]["/items/{id}"]["get"]
    assert "404" in path["responses"]
    assert path["responses"]["404"]["description"] == "Item not found"
    assert "403" in path["responses"]


# ---------------------------------------------------------------------------
#  Router-level dependencies
# ---------------------------------------------------------------------------


def test_router_level_dependencies():
    called: list[str] = []

    async def router_dep():
        called.append("router_dep")

    router = FasterRouter(prefix="/api", dependencies=[Depends(router_dep)])

    @router.get("/hello")
    async def hello():
        return {"msg": "hi"}

    app = Faster()
    app.include_router(router)

    client = TestClient(app)
    resp = client.get("/api/hello")
    assert resp.status_code == 200
    assert "router_dep" in called


def test_include_router_with_dependencies():
    called: list[str] = []

    async def extra_dep():
        called.append("extra")

    router = FasterRouter(prefix="/r")

    @router.get("/x")
    async def x():
        return {"x": 1}

    app = Faster()
    app.include_router(router, dependencies=[Depends(extra_dep)])

    client = TestClient(app)
    resp = client.get("/r/x")
    assert resp.status_code == 200
    assert "extra" in called


# ---------------------------------------------------------------------------
#  Dataclass support
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Item:
    name: str
    price: float
    in_stock: bool = True


def test_dataclass_request_body():
    app = Faster()

    @app.post("/items")
    async def create_item(item: Item):
        return {"name": item.name, "price": item.price}

    client = TestClient(app)
    resp = client.post("/items", json={"name": "Widget", "price": 9.99})
    assert resp.status_code == 200
    assert resp.json() == {"name": "Widget", "price": 9.99}


def test_dataclass_openapi_schema():
    from FasterAPI.openapi.generator import generate_openapi

    app = Faster()

    @app.post("/items")
    async def create_item(item: Item):
        return item

    spec = generate_openapi(app, title="T", version="0")
    assert "Item" in spec.get("components", {}).get("schemas", {})


# ---------------------------------------------------------------------------
#  Enum path parameters in OpenAPI
# ---------------------------------------------------------------------------


class Color(enum.Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


def test_enum_path_param_openapi():
    from FasterAPI.openapi.generator import generate_openapi

    app = Faster()

    @app.get("/items/{color}")
    async def get_by_color(color: Color):
        return {"color": color.value}

    spec = generate_openapi(app, title="T", version="0")
    params = spec["paths"]["/items/{color}"]["get"]["parameters"]
    color_param = next(p for p in params if p["name"] == "color")
    assert "enum" in color_param["schema"]
    assert "red" in color_param["schema"]["enum"]


# ---------------------------------------------------------------------------
#  openapi_tags / terms_of_service / contact / license_info
# ---------------------------------------------------------------------------


def test_openapi_metadata():
    from FasterAPI.openapi.generator import generate_openapi

    app = Faster(
        openapi_tags=[{"name": "users", "description": "User operations"}],
        terms_of_service="https://example.com/tos",
        contact={"name": "Support", "email": "support@example.com"},
        license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
    )

    @app.get("/users", tags=["users"])
    async def list_users():
        return []

    spec = generate_openapi(
        app,
        title="MyAPI",
        version="1.0",
        openapi_tags=app.openapi_tags,
        terms_of_service=app.terms_of_service,
        contact=app.contact,
        license_info=app.license_info,
    )

    assert spec["info"]["termsOfService"] == "https://example.com/tos"
    assert spec["info"]["contact"]["name"] == "Support"
    assert spec["info"]["license"]["name"] == "MIT"
    assert any(t["name"] == "users" for t in spec.get("tags", []))


def test_openapi_tags_via_app_route():
    app = Faster()

    @app.get("/ping")
    async def ping():
        return "pong"

    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
