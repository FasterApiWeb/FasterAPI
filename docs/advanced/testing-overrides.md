# Testing with Dependency Overrides

Replace real dependencies (databases, external services, auth) with test doubles
during testing, without changing production code.

## Setup

Install the testing extras:

```bash
pip install faster-api-web[test]   # includes httpx
pip install pytest pytest-asyncio
```

## Basic test with `TestClient`

```python
# main.py
from FasterAPI import Faster, Depends

app = Faster()


async def get_db():
    return {"host": "postgres://prod"}


@app.get("/items")
async def list_items(db: dict = Depends(get_db)):
    return {"db_host": db["host"]}
```

```python
# tests/test_main.py
from FasterAPI import TestClient
from main import app, get_db

client = TestClient(app)


def test_list_items_with_real_dep():
    response = client.get("/items")
    assert response.status_code == 200
```

## Overriding dependencies

```python
# tests/test_main.py
from FasterAPI import TestClient
from main import app, get_db

client = TestClient(app)


def fake_db():
    return {"host": "sqlite:///:memory:"}


def test_with_fake_db():
    app.dependency_overrides[get_db] = fake_db
    response = client.get("/items")
    assert response.json() == {"db_host": "sqlite:///:memory:"}
    app.dependency_overrides.clear()
```

!!! tip
    Always clear overrides after each test to avoid state leaking between tests.

## Using pytest fixtures

```python
import pytest
from FasterAPI import TestClient
from main import app, get_db


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: {"host": "sqlite:///:memory:"}
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_items(client):
    r = client.get("/items")
    assert r.status_code == 200
```

## Overriding auth dependencies

```python
# auth.py
from FasterAPI import Header, HTTPException


async def get_current_user(authorization: str = Header()):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401)
    token = authorization.removeprefix("Bearer ")
    # validate JWT in production
    return {"user_id": 1, "token": token}
```

```python
# tests/conftest.py
import pytest
from FasterAPI import TestClient
from main import app
from auth import get_current_user


@pytest.fixture
def authenticated_client():
    async def fake_user():
        return {"user_id": 42, "token": "test-token"}

    app.dependency_overrides[get_current_user] = fake_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

## Testing error paths

```python
def test_missing_item(client):
    r = client.get("/items/9999")
    assert r.status_code == 404
    assert r.json()["detail"] == "Not found"
```

## Testing with request headers

```python
def test_requires_auth(client):
    r = client.get("/me")
    assert r.status_code == 401

def test_authenticated(authenticated_client):
    r = authenticated_client.get("/me")
    assert r.status_code == 200
```

## TestClient and lifespan

`TestClient` triggers `on_startup` / `on_shutdown` handlers when used as a context
manager:

```python
with TestClient(app) as client:
    # startup handlers have run
    r = client.get("/items")
# shutdown handlers have run
```

## Next steps

- [Async Tests](async-tests.md) — test async code with `pytest-asyncio`.
- [Dependencies](../tutorial/dependencies.md) — understand the DI system being overridden.
