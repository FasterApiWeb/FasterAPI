"""Integration tests using TestClient with a full CRUD app — no real server needed."""

from __future__ import annotations

import msgspec
import pytest

from FasterAPI import (
    BackgroundTasks,
    Depends,
    Faster,
    FasterRouter,
    HTTPException,
    TestClient,
)
from FasterAPI.params import Body, Cookie, File, Form, Header, Path, Query
from FasterAPI.request import Request
from FasterAPI.response import JSONResponse, PlainTextResponse, RedirectResponse
from FasterAPI.datastructures import UploadFile


# ==============================
#  Build a small CRUD app
# ==============================

class Item(msgspec.Struct):
    name: str
    price: float
    in_stock: bool = True


# In-memory store
ITEMS: dict[str, dict] = {}


def build_app() -> Faster:
    app = Faster(title="TestApp", version="1.0.0", description="Integration test app")

    # --- Auth dependency ---

    async def require_auth(request: Request):
        token = request.headers.get("authorization")
        if token != "Bearer secret":
            raise HTTPException(status_code=401, detail="Unauthorized")
        return {"user": "admin"}

    # --- CRUD routes ---

    @app.get("/items", tags=["items"])
    async def list_items():
        return list(ITEMS.values())

    @app.get("/items/{item_id}", tags=["items"])
    async def get_item(item_id: str = Path()):
        if item_id not in ITEMS:
            raise HTTPException(status_code=404, detail="Item not found")
        return ITEMS[item_id]

    @app.post("/items", tags=["items"], status_code=201)
    async def create_item(item: Item):
        item_id = str(len(ITEMS) + 1)
        data = {"id": item_id, "name": item.name, "price": item.price, "in_stock": item.in_stock}
        ITEMS[item_id] = data
        return data

    @app.put("/items/{item_id}", tags=["items"])
    async def update_item(item: Item, item_id: str = Path()):
        if item_id not in ITEMS:
            raise HTTPException(status_code=404, detail="Item not found")
        ITEMS[item_id].update(name=item.name, price=item.price, in_stock=item.in_stock)
        return ITEMS[item_id]

    @app.delete("/items/{item_id}", tags=["items"])
    async def delete_item(item_id: str = Path(), auth=Depends(require_auth)):
        if item_id not in ITEMS:
            raise HTTPException(status_code=404, detail="Item not found")
        deleted = ITEMS.pop(item_id)
        return {"deleted": deleted["id"]}

    @app.patch("/items/{item_id}/price", tags=["items"])
    async def update_price(item_id: str = Path(), price: dict = Body()):
        if item_id not in ITEMS:
            raise HTTPException(status_code=404, detail="Item not found")
        ITEMS[item_id]["price"] = price["price"]
        return ITEMS[item_id]

    # --- Query params ---

    @app.get("/search")
    async def search(q: str = Query(""), limit: str = Query("10")):
        results = [v for v in ITEMS.values() if q.lower() in v["name"].lower()]
        return results[: int(limit)]

    # --- Header params ---

    @app.get("/whoami")
    async def whoami(authorization: str = Header("none")):
        return {"auth": authorization}

    # --- Cookie params ---

    @app.get("/session")
    async def session_info(session_id: str = Cookie("anon")):
        return {"session": session_id}

    # --- Background tasks ---

    @app.post("/notify")
    async def notify(bg: BackgroundTasks):
        bg.add_task(lambda: None)  # no-op task for testing
        return {"queued": True}

    # --- Response types ---

    @app.get("/text")
    async def text_response():
        return PlainTextResponse("hello")

    @app.get("/redirect")
    async def redirect():
        return RedirectResponse("/items")

    @app.get("/json-response")
    async def custom_json():
        return JSONResponse({"custom": True}, status_code=202)

    # --- Form endpoint ---

    @app.post("/form")
    async def form_submit(name: str = Form(), email: str = Form("none")):
        return {"name": name, "email": email}

    # --- File upload ---

    @app.post("/upload")
    async def upload(file: UploadFile = File(), label: str = Form("untitled")):
        data = await file.read()
        return {"filename": file.filename, "size": len(data), "label": label}

    # --- Sub-router ---

    api_v2 = FasterRouter(prefix="/api/v2", tags=["v2"])

    @api_v2.get("/ping")
    async def ping():
        return {"pong": True}

    @api_v2.get("/echo/{msg}")
    async def echo(msg: str = Path()):
        return {"echo": msg}

    app.include_router(api_v2)

    return app


# ==============================
#  Tests
# ==============================

@pytest.fixture(autouse=True)
def clear_store():
    ITEMS.clear()
    yield
    ITEMS.clear()


@pytest.fixture
def client():
    app = build_app()
    with TestClient(app) as c:
        yield c


class TestCRUDLifecycle:
    def test_create_item(self, client):
        resp = client.post("/items", json={"name": "Widget", "price": 9.99})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Widget"
        assert data["price"] == 9.99
        assert data["in_stock"] is True
        assert "id" in data

    def test_list_items_empty(self, client):
        resp = client.get("/items")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_full_crud_lifecycle(self, client):
        # Create
        resp = client.post("/items", json={"name": "Gadget", "price": 19.99})
        assert resp.status_code == 201
        item_id = resp.json()["id"]

        # Read
        resp = client.get(f"/items/{item_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Gadget"

        # List
        resp = client.get("/items")
        assert len(resp.json()) == 1

        # Update
        resp = client.put(f"/items/{item_id}", json={"name": "Super Gadget", "price": 29.99})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Super Gadget"

        # Patch
        resp = client.patch(f"/items/{item_id}/price", json={"price": 24.99})
        assert resp.status_code == 200
        assert resp.json()["price"] == 24.99

        # Delete (requires auth)
        resp = client.delete(f"/items/{item_id}", headers={"Authorization": "Bearer secret"})
        assert resp.status_code == 200
        assert resp.json()["deleted"] == item_id

        # Verify gone
        resp = client.get(f"/items/{item_id}")
        assert resp.status_code == 404

    def test_create_multiple_items(self, client):
        client.post("/items", json={"name": "A", "price": 1.0})
        client.post("/items", json={"name": "B", "price": 2.0})
        client.post("/items", json={"name": "C", "price": 3.0})
        resp = client.get("/items")
        assert len(resp.json()) == 3


class TestHTTPExceptions:
    def test_404_not_found(self, client):
        resp = client.get("/items/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Item not found"

    def test_401_unauthorized(self, client):
        client.post("/items", json={"name": "X", "price": 1.0})
        resp = client.delete("/items/1")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Unauthorized"

    def test_delete_with_auth(self, client):
        client.post("/items", json={"name": "X", "price": 1.0})
        resp = client.delete("/items/1", headers={"Authorization": "Bearer secret"})
        assert resp.status_code == 200

    def test_invalid_json_body(self, client):
        resp = client.post(
            "/items",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422


class TestQueryParams:
    def test_search_empty(self, client):
        resp = client.get("/search")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_search_with_results(self, client):
        client.post("/items", json={"name": "Blue Widget", "price": 5.0})
        client.post("/items", json={"name": "Red Gadget", "price": 10.0})
        client.post("/items", json={"name": "Blue Gadget", "price": 15.0})

        resp = client.get("/search?q=blue")
        assert len(resp.json()) == 2

    def test_search_with_limit(self, client):
        client.post("/items", json={"name": "A", "price": 1.0})
        client.post("/items", json={"name": "AB", "price": 2.0})
        client.post("/items", json={"name": "ABC", "price": 3.0})

        resp = client.get("/search?q=A&limit=2")
        assert len(resp.json()) == 2


class TestHeaderParams:
    def test_header_default(self, client):
        resp = client.get("/whoami")
        assert resp.json()["auth"] == "none"

    def test_header_provided(self, client):
        resp = client.get("/whoami", headers={"Authorization": "Bearer tok"})
        assert resp.json()["auth"] == "Bearer tok"


class TestCookieParams:
    def test_cookie_default(self, client):
        resp = client.get("/session")
        assert resp.json()["session"] == "anon"

    def test_cookie_provided(self, client):
        resp = client.get("/session", cookies={"session_id": "sess123"})
        assert resp.json()["session"] == "sess123"


class TestBackgroundTasks:
    def test_background_task_endpoint(self, client):
        resp = client.post("/notify")
        assert resp.status_code == 200
        assert resp.json()["queued"] is True


class TestResponseTypes:
    def test_plain_text(self, client):
        resp = client.get("/text")
        assert resp.status_code == 200
        assert resp.text == "hello"

    def test_redirect(self, client):
        resp = client.get("/redirect", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"] == "/items"

    def test_custom_json_status(self, client):
        resp = client.get("/json-response")
        assert resp.status_code == 202
        assert resp.json() == {"custom": True}


class TestFormEndpoints:
    def test_urlencoded_form(self, client):
        resp = client.post(
            "/form",
            data={"name": "Alice", "email": "alice@example.com"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"name": "Alice", "email": "alice@example.com"}

    def test_form_default_value(self, client):
        resp = client.post("/form", data={"name": "Bob"})
        assert resp.json() == {"name": "Bob", "email": "none"}

    def test_file_upload(self, client):
        resp = client.post(
            "/upload",
            files={"file": ("test.txt", b"hello world", "text/plain")},
            data={"label": "my file"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["filename"] == "test.txt"
        assert body["size"] == 11
        assert body["label"] == "my file"


class TestSubRouter:
    def test_sub_router_ping(self, client):
        resp = client.get("/api/v2/ping")
        assert resp.status_code == 200
        assert resp.json() == {"pong": True}

    def test_sub_router_echo(self, client):
        resp = client.get("/api/v2/echo/hello")
        assert resp.status_code == 200
        assert resp.json() == {"echo": "hello"}


class TestOpenAPI:
    def test_openapi_schema(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        spec = resp.json()
        assert spec["openapi"] == "3.0.3"
        assert spec["info"]["title"] == "TestApp"
        assert spec["info"]["version"] == "1.0.0"
        assert "/items" in spec["paths"]

    def test_swagger_docs(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200
        assert "swagger" in resp.text.lower()

    def test_redoc(self, client):
        resp = client.get("/redoc")
        assert resp.status_code == 200
        assert "redoc" in resp.text.lower()


class TestContextManager:
    def test_client_as_context_manager(self):
        app = build_app()
        with TestClient(app) as client:
            resp = client.get("/items")
            assert resp.status_code == 200

    def test_custom_base_url(self):
        app = build_app()
        client = TestClient(app, base_url="http://myapp.test")
        resp = client.get("/items")
        assert resp.status_code == 200


class TestEdgeCases:
    def test_trailing_slash(self, client):
        resp = client.get("/items/")
        # Should still work due to trailing slash normalization
        assert resp.status_code == 200

    def test_unknown_route(self, client):
        resp = client.get("/nonexistent")
        assert resp.status_code == 404

    def test_method_not_on_route(self, client):
        # PUT on /items (only GET and POST registered)
        resp = client.put("/items", json={"name": "X", "price": 1.0})
        assert resp.status_code == 404

    def test_options_request(self, client):
        resp = client.options("/items")
        # No OPTIONS handler registered, so 404
        assert resp.status_code == 404

    def test_head_request(self, client):
        resp = client.head("/items")
        # No HEAD handler, 404
        assert resp.status_code == 404
