"""TestClient HTTP and WebSocket paths."""

import msgspec
import pytest

from FasterAPI import Faster
from FasterAPI.testclient import TestClient


@pytest.fixture
def simple_app():
    app = Faster(openapi_url=None, docs_url=None, redoc_url=None)

    @app.get("/hello")
    async def hello():
        return {"msg": "ok"}

    @app.post("/echo")
    async def echo():
        return {"received": True}

    return app


def test_testclient_get_json(simple_app):
    with TestClient(simple_app) as client:
        r = client.get("/hello")
        assert r.status_code == 200
        assert r.json()["msg"] == "ok"


def test_testclient_post(simple_app):
    with TestClient(simple_app) as client:
        r = client.post("/echo")
        assert r.status_code == 200


def test_testclient_methods_smoke(simple_app):
    app = simple_app

    @app.put("/p")
    async def p():
        return {}

    @app.delete("/d")
    async def d():
        return {}

    @app.patch("/a")
    async def a():
        return {}

    with TestClient(app) as c:
        assert c.put("/p").status_code == 200
        assert c.delete("/d").status_code == 200
        assert c.patch("/a").status_code == 200
