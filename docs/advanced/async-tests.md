# Async Tests

FasterAPI handlers are async coroutines.  Use **pytest-asyncio** to test them
directly without going through HTTP, or combine with `TestClient` for full
integration testing.

## Installation

```bash
pip install pytest pytest-asyncio httpx
pip install faster-api-web[test]
```

## Configuring pytest-asyncio

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Or per-file with a marker:

```python
import pytest
pytestmark = pytest.mark.asyncio
```

## Testing handler functions directly

Call the handler as a coroutine without HTTP overhead:

```python
# main.py
import msgspec
from FasterAPI import Faster

app = Faster()


class Item(msgspec.Struct):
    name: str
    price: float


@app.get("/items/{item_id}")
async def get_item(item_id: int) -> Item:
    return Item(id=item_id, name="Widget", price=9.99)
```

```python
# tests/test_handlers.py
import pytest
from main import get_item


@pytest.mark.asyncio
async def test_get_item():
    result = await get_item(item_id=1)
    assert result.name == "Widget"
    assert result.price == 9.99
```

## Async fixtures

```python
import pytest_asyncio


@pytest_asyncio.fixture
async def db_session():
    session = await open_test_db()
    yield session
    await session.close()


@pytest.mark.asyncio
async def test_with_db(db_session):
    rows = await db_session.fetch("SELECT 1")
    assert rows is not None
```

## Async TestClient

Use `httpx.AsyncClient` with the ASGI transport for fully async integration tests:

```python
import pytest
import httpx
from main import app


@pytest.mark.asyncio
async def test_list_items_async():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.get("/items")
        assert r.status_code == 200
```

## Concurrent requests

Test that concurrent requests behave correctly:

```python
import asyncio


@pytest.mark.asyncio
async def test_concurrent_requests():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        tasks = [client.get("/items") for _ in range(10)]
        responses = await asyncio.gather(*tasks)
        assert all(r.status_code == 200 for r in responses)
```

## Testing WebSockets

```python
from FasterAPI import TestClient
from main import app


def test_websocket():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text("hello")
        data = ws.receive_text()
        assert data == "Echo: hello"
```

## Testing lifespan events

```python
@pytest.fixture
def app_with_lifespan():
    from FasterAPI import Faster
    test_app = Faster()
    state = {}

    @test_app.on_startup
    async def startup():
        state["db"] = "connected"

    @test_app.get("/status")
    async def status():
        return {"db": state.get("db")}

    return test_app, state


def test_startup_ran(app_with_lifespan):
    test_app, state = app_with_lifespan
    with TestClient(test_app) as client:
        r = client.get("/status")
        assert r.json()["db"] == "connected"
```

## Coverage

Run with coverage:

```bash
pytest --cov=. --cov-report=term-missing
```

## Next steps

- [Testing with Overrides](testing-overrides.md) — swap dependencies in tests.
- [Dependencies](../tutorial/dependencies.md) — understand what you're testing.
