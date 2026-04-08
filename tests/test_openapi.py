from __future__ import annotations

from typing import Optional

import msgspec
import pytest

from FasterAPI.app import Faster
from FasterAPI.dependencies import Depends
from FasterAPI.openapi.generator import generate_openapi
from FasterAPI.openapi.ui import redoc_html, swagger_ui_html
from FasterAPI.params import Body, Cookie, Header, Path, Query
from FasterAPI.request import Request


# --------------- models ---------------

class Item(msgspec.Struct):
    """An item in the store."""
    name: str
    price: float
    in_stock: bool = True


class ItemUpdate(msgspec.Struct):
    name: str | None = None
    price: float | None = None


class User(msgspec.Struct):
    username: str
    email: str
    items: list[Item] = []


# --------------- helpers ---------------

def _make_app(**kw) -> Faster:
    return Faster(**kw)


# ==============================
#  OpenAPI spec structure
# ==============================

class TestSpecStructure:
    def test_basic_structure(self):
        app = _make_app(title="TestApp", version="2.0.0", description="A test app")

        @app.get("/health")
        async def health():
            return {"ok": True}

        spec = generate_openapi(app, title="TestApp", version="2.0.0", description="A test app")

        assert spec["openapi"] == "3.0.3"
        assert spec["info"]["title"] == "TestApp"
        assert spec["info"]["version"] == "2.0.0"
        assert spec["info"]["description"] == "A test app"
        assert "paths" in spec

    def test_no_description_omitted(self):
        app = _make_app()
        spec = generate_openapi(app)
        assert "description" not in spec["info"]

    def test_paths_populated(self):
        app = _make_app()

        @app.get("/users")
        async def list_users():
            return []

        @app.post("/users")
        async def create_user():
            return {}

        spec = generate_openapi(app)
        assert "/users" in spec["paths"]
        assert "get" in spec["paths"]["/users"]
        assert "post" in spec["paths"]["/users"]


# ==============================
#  Path parameters
# ==============================

class TestPathParams:
    def test_path_param_in_spec(self):
        app = _make_app()

        @app.get("/users/{user_id}")
        async def get_user(user_id: str = Path()):
            return {}

        spec = generate_openapi(app)
        op = spec["paths"]["/users/{user_id}"]["get"]
        params = op["parameters"]
        path_params = [p for p in params if p["in"] == "path"]

        assert len(path_params) == 1
        assert path_params[0]["name"] == "user_id"
        assert path_params[0]["required"] is True
        assert path_params[0]["schema"]["type"] == "string"

    def test_path_param_int_type(self):
        app = _make_app()

        @app.get("/items/{item_id}")
        async def get_item(item_id: int = Path()):
            return {}

        spec = generate_openapi(app)
        param = spec["paths"]["/items/{item_id}"]["get"]["parameters"][0]
        assert param["schema"]["type"] == "integer"

    def test_path_param_with_description(self):
        app = _make_app()

        @app.get("/users/{user_id}")
        async def get_user(user_id: str = Path(description="The user ID")):
            return {}

        spec = generate_openapi(app)
        param = spec["paths"]["/users/{user_id}"]["get"]["parameters"][0]
        assert param["description"] == "The user ID"


# ==============================
#  Query parameters
# ==============================

class TestQueryParams:
    def test_query_param(self):
        app = _make_app()

        @app.get("/search")
        async def search(q: str = Query(description="Search query")):
            return []

        spec = generate_openapi(app)
        params = spec["paths"]["/search"]["get"]["parameters"]
        query_params = [p for p in params if p["in"] == "query"]

        assert len(query_params) == 1
        assert query_params[0]["name"] == "q"
        assert query_params[0]["description"] == "Search query"

    def test_query_param_with_default(self):
        app = _make_app()

        @app.get("/items")
        async def list_items(skip: int = Query(0), limit: int = Query(10)):
            return []

        spec = generate_openapi(app)
        params = spec["paths"]["/items"]["get"]["parameters"]

        skip_param = next(p for p in params if p["name"] == "skip")
        assert skip_param["schema"]["default"] == 0

        limit_param = next(p for p in params if p["name"] == "limit")
        assert limit_param["schema"]["default"] == 10

    def test_query_param_alias(self):
        app = _make_app()

        @app.get("/items")
        async def list_items(q: str = Query(alias="search_query")):
            return []

        spec = generate_openapi(app)
        param = spec["paths"]["/items"]["get"]["parameters"][0]
        assert param["name"] == "search_query"


# ==============================
#  Header parameters
# ==============================

class TestHeaderParams:
    def test_header_param(self):
        app = _make_app()

        @app.get("/secure")
        async def secure(x_token: str = Header()):
            return {}

        spec = generate_openapi(app)
        params = spec["paths"]["/secure"]["get"]["parameters"]
        header_params = [p for p in params if p["in"] == "header"]

        assert len(header_params) == 1
        assert header_params[0]["name"] == "x-token"

    def test_header_alias(self):
        app = _make_app()

        @app.get("/auth")
        async def auth(token: str = Header(alias="Authorization")):
            return {}

        spec = generate_openapi(app)
        param = spec["paths"]["/auth"]["get"]["parameters"][0]
        assert param["name"] == "Authorization"


# ==============================
#  Cookie parameters
# ==============================

class TestCookieParams:
    def test_cookie_param(self):
        app = _make_app()

        @app.get("/me")
        async def me(session: str = Cookie()):
            return {}

        spec = generate_openapi(app)
        params = spec["paths"]["/me"]["get"]["parameters"]
        cookie_params = [p for p in params if p["in"] == "cookie"]

        assert len(cookie_params) == 1
        assert cookie_params[0]["name"] == "session"


# ==============================
#  Request body (structs)
# ==============================

class TestRequestBody:
    def test_struct_body(self):
        app = _make_app()

        @app.post("/items")
        async def create_item(item: Item):
            return {}

        spec = generate_openapi(app)
        op = spec["paths"]["/items"]["post"]

        assert "requestBody" in op
        rb = op["requestBody"]
        assert rb["required"] is True
        schema = rb["content"]["application/json"]["schema"]
        assert schema["$ref"] == "#/components/schemas/Item"

        # Check component
        item_schema = spec["components"]["schemas"]["Item"]
        assert item_schema["type"] == "object"
        assert "name" in item_schema["properties"]
        assert "price" in item_schema["properties"]
        assert "in_stock" in item_schema["properties"]
        assert "name" in item_schema["required"]
        assert "price" in item_schema["required"]
        assert "in_stock" not in item_schema["required"]

    def test_struct_description_from_docstring(self):
        app = _make_app()

        @app.post("/items")
        async def create(item: Item):
            return {}

        spec = generate_openapi(app)
        assert spec["components"]["schemas"]["Item"]["description"] == "An item in the store."

    def test_struct_field_types(self):
        app = _make_app()

        @app.post("/items")
        async def create(item: Item):
            return {}

        spec = generate_openapi(app)
        props = spec["components"]["schemas"]["Item"]["properties"]

        assert props["name"]["type"] == "string"
        assert props["price"]["type"] == "number"
        assert props["in_stock"]["type"] == "boolean"

    def test_nested_struct(self):
        app = _make_app()

        @app.post("/users")
        async def create_user(user: User):
            return {}

        spec = generate_openapi(app)
        user_schema = spec["components"]["schemas"]["User"]
        items_prop = user_schema["properties"]["items"]
        assert items_prop["type"] == "array"
        assert items_prop["items"]["$ref"] == "#/components/schemas/Item"

    def test_struct_reuse(self):
        """Same struct used in two routes should only appear once in components."""
        app = _make_app()

        @app.post("/items")
        async def create(item: Item):
            return {}

        @app.put("/items/{id}")
        async def update(id: str = Path(), item: Item = Body()):
            return {}

        spec = generate_openapi(app)
        # Item only appears once
        assert "Item" in spec["components"]["schemas"]
        assert spec["components"]["schemas"]["Item"]["type"] == "object"


# ==============================
#  Response model
# ==============================

class TestResponseModel:
    def test_response_model_ref(self):
        app = _make_app()

        @app.get("/items/{id}", response_model=Item)
        async def get_item(id: str = Path()):
            return {}

        spec = generate_openapi(app)
        resp = spec["paths"]["/items/{id}"]["get"]["responses"]["200"]
        assert resp["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/Item"

    def test_no_response_model(self):
        app = _make_app()

        @app.get("/ping")
        async def ping():
            return "pong"

        spec = generate_openapi(app)
        resp = spec["paths"]["/ping"]["get"]["responses"]["200"]
        assert resp["description"] == "Successful Response"
        assert "content" not in resp


# ==============================
#  Tags, summary, deprecated
# ==============================

class TestMetadata:
    def test_tags(self):
        app = _make_app()

        @app.get("/items", tags=["items"])
        async def list_items():
            return []

        spec = generate_openapi(app)
        op = spec["paths"]["/items"]["get"]
        assert op["tags"] == ["items"]

    def test_summary_from_decorator(self):
        app = _make_app()

        @app.get("/items", summary="List all items")
        async def list_items():
            return []

        spec = generate_openapi(app)
        assert spec["paths"]["/items"]["get"]["summary"] == "List all items"

    def test_summary_from_function_name(self):
        app = _make_app()

        @app.get("/items")
        async def list_all_items():
            return []

        spec = generate_openapi(app)
        assert spec["paths"]["/items"]["get"]["summary"] == "List All Items"

    def test_description_from_docstring(self):
        app = _make_app()

        @app.get("/items")
        async def list_items():
            """Return all items in the database."""
            return []

        spec = generate_openapi(app)
        assert spec["paths"]["/items"]["get"]["description"] == "Return all items in the database."

    def test_deprecated(self):
        app = _make_app()

        @app.get("/old", deprecated=True)
        async def old():
            return {}

        spec = generate_openapi(app)
        assert spec["paths"]["/old"]["get"]["deprecated"] is True

    def test_operation_id(self):
        app = _make_app()

        @app.get("/items")
        async def list_items():
            return []

        spec = generate_openapi(app)
        assert spec["paths"]["/items"]["get"]["operationId"] == "list_items"


# ==============================
#  422 validation error response
# ==============================

class TestValidationResponse:
    def test_422_added_when_params_exist(self):
        app = _make_app()

        @app.get("/items/{id}")
        async def get_item(id: str = Path()):
            return {}

        spec = generate_openapi(app)
        responses = spec["paths"]["/items/{id}"]["get"]["responses"]
        assert "422" in responses

    def test_no_422_when_no_params(self):
        app = _make_app()

        @app.get("/ping")
        async def ping():
            return "pong"

        spec = generate_openapi(app)
        responses = spec["paths"]["/ping"]["get"]["responses"]
        assert "422" not in responses


# ==============================
#  Caching
# ==============================

class TestCaching:
    def test_spec_is_cached(self):
        app = _make_app()

        @app.get("/ping")
        async def ping():
            return "pong"

        spec1 = generate_openapi(app)
        spec2 = generate_openapi(app)
        assert spec1 is spec2


# ==============================
#  Type mapping
# ==============================

class ListModel(msgspec.Struct):
    tags: list[str]


class DictModel(msgspec.Struct):
    metadata: dict[str, int]


class TestTypeMapping:
    def test_optional_nullable(self):
        app = _make_app()

        @app.put("/items/{id}")
        async def update(id: str = Path(), item: ItemUpdate = Body()):
            return {}

        spec = generate_openapi(app)
        props = spec["components"]["schemas"]["ItemUpdate"]["properties"]
        assert props["name"].get("nullable") is True
        assert props["price"].get("nullable") is True

    def test_list_type(self):
        app = _make_app()

        @app.post("/tagged")
        async def create(model: ListModel):
            return {}

        spec = generate_openapi(app)
        props = spec["components"]["schemas"]["ListModel"]["properties"]
        assert props["tags"]["type"] == "array"
        assert props["tags"]["items"]["type"] == "string"

    def test_dict_type(self):
        app = _make_app()

        @app.post("/meta")
        async def create(model: DictModel):
            return {}

        spec = generate_openapi(app)
        props = spec["components"]["schemas"]["DictModel"]["properties"]
        assert props["metadata"]["type"] == "object"
        assert props["metadata"]["additionalProperties"]["type"] == "integer"


# ==============================
#  UI HTML
# ==============================

class TestUI:
    def test_swagger_html_contains_url(self):
        html = swagger_ui_html("/openapi.json", title="My App")
        assert "/openapi.json" in html
        assert "My App" in html
        assert "swagger-ui" in html

    def test_redoc_html_contains_url(self):
        html = redoc_html("/openapi.json", title="My App")
        assert "/openapi.json" in html
        assert "My App" in html
        assert "redoc" in html


# ==============================
#  Auto-registered routes in app
# ==============================

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


class TestAutoRoutes:
    @pytest.mark.asyncio
    async def test_openapi_json_route(self):
        app = _make_app()

        @app.get("/items")
        async def items():
            return []

        send = MockSend()
        scope = {
            "type": "http", "method": "GET", "path": "/openapi.json",
            "headers": [], "query_string": b"",
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        await app(scope, receive, send)
        assert send.status == 200

        spec = msgspec.json.decode(send.body)
        assert spec["openapi"] == "3.0.3"
        assert "/items" in spec["paths"]

    @pytest.mark.asyncio
    async def test_docs_route(self):
        app = _make_app()
        send = MockSend()
        scope = {
            "type": "http", "method": "GET", "path": "/docs",
            "headers": [], "query_string": b"",
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        await app(scope, receive, send)
        assert send.status == 200
        assert b"swagger-ui" in send.body

    @pytest.mark.asyncio
    async def test_redoc_route(self):
        app = _make_app()
        send = MockSend()
        scope = {
            "type": "http", "method": "GET", "path": "/redoc",
            "headers": [], "query_string": b"",
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        await app(scope, receive, send)
        assert send.status == 200
        assert b"redoc" in send.body

    @pytest.mark.asyncio
    async def test_disabled_openapi(self):
        app = Faster(openapi_url=None)
        send = MockSend()
        scope = {
            "type": "http", "method": "GET", "path": "/openapi.json",
            "headers": [], "query_string": b"",
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        await app(scope, receive, send)
        assert send.status == 404

    @pytest.mark.asyncio
    async def test_custom_urls(self):
        app = Faster(openapi_url="/api/schema", docs_url="/api/docs", redoc_url="/api/redoc")
        send = MockSend()

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        # /api/schema should work
        await app(
            {"type": "http", "method": "GET", "path": "/api/schema", "headers": [], "query_string": b""},
            receive, send,
        )
        assert send.status == 200


# ==============================
#  Combined: complex app spec
# ==============================

class TestComplexSpec:
    def test_full_crud_spec(self):
        app = _make_app(title="ItemStore", version="1.0.0")

        @app.get("/items", tags=["items"], summary="List items", response_model=list[Item])
        async def list_items(skip: int = Query(0), limit: int = Query(10)):
            return []

        @app.post("/items", tags=["items"], summary="Create item", status_code=201, response_model=Item)
        async def create_item(item: Item):
            return item

        @app.get("/items/{item_id}", tags=["items"], response_model=Item)
        async def get_item(item_id: int = Path(description="The item ID")):
            return {}

        @app.delete("/items/{item_id}", tags=["items"], status_code=204)
        async def delete_item(item_id: int = Path()):
            return None

        spec = generate_openapi(app, title="ItemStore", version="1.0.0")

        # Structure checks
        assert spec["openapi"] == "3.0.3"
        assert spec["info"]["title"] == "ItemStore"

        # All paths present
        assert "/items" in spec["paths"]
        assert "/items/{item_id}" in spec["paths"]

        # GET /items
        get_items = spec["paths"]["/items"]["get"]
        assert get_items["tags"] == ["items"]
        assert get_items["summary"] == "List items"
        query_names = {p["name"] for p in get_items["parameters"]}
        assert query_names == {"skip", "limit"}

        # POST /items
        post_items = spec["paths"]["/items"]["post"]
        assert "requestBody" in post_items
        resp_schema = post_items["responses"]["201"]["content"]["application/json"]["schema"]
        assert resp_schema["$ref"] == "#/components/schemas/Item"

        # GET /items has list[Item] response model
        get_items_resp = get_items["responses"]["200"]["content"]["application/json"]["schema"]
        assert get_items_resp["type"] == "array"
        assert get_items_resp["items"]["$ref"] == "#/components/schemas/Item"

        # GET /items/{item_id}
        get_item_op = spec["paths"]["/items/{item_id}"]["get"]
        path_params = [p for p in get_item_op["parameters"] if p["in"] == "path"]
        assert path_params[0]["name"] == "item_id"
        assert path_params[0]["schema"]["type"] == "integer"
        assert path_params[0]["description"] == "The item ID"

        # DELETE /items/{item_id}
        delete_op = spec["paths"]["/items/{item_id}"]["delete"]
        assert "204" in delete_op["responses"]

        # Components
        assert "Item" in spec["components"]["schemas"]

    def test_depends_skipped_in_params(self):
        """Depends() parameters should not appear in OpenAPI params."""
        app = _make_app()

        async def get_db():
            return "db"

        @app.get("/items")
        async def list_items(db=Depends(get_db), q: str = Query()):
            return []

        spec = generate_openapi(app)
        params = spec["paths"]["/items"]["get"]["parameters"]
        param_names = [p["name"] for p in params]
        assert "db" not in param_names
        assert "q" in param_names

    def test_request_skipped_in_params(self):
        """Request parameters should not appear in OpenAPI params."""
        app = _make_app()

        @app.get("/info")
        async def info(request: Request):
            return {}

        spec = generate_openapi(app)
        op = spec["paths"]["/info"]["get"]
        assert "parameters" not in op or len(op.get("parameters", [])) == 0
