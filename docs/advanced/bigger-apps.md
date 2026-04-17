# Bigger Applications

As your project grows, organise routes into separate modules and routers.  This page
shows a recommended layout for a medium-to-large FasterAPI project.

## Recommended project layout

```
myproject/
├── main.py                  # Faster() app, includes all routers
├── config.py                # Settings / env vars
├── dependencies.py          # Shared Depends() callables
├── models/
│   ├── __init__.py
│   ├── item.py              # Item, ItemCreate, ItemUpdate structs
│   └── user.py              # User, UserCreate structs
├── routers/
│   ├── __init__.py
│   ├── items.py             # FasterRouter for /items
│   ├── users.py             # FasterRouter for /users
│   └── auth.py              # FasterRouter for /auth
├── services/
│   ├── __init__.py
│   ├── item_service.py      # Business logic (no HTTP)
│   └── user_service.py
└── tests/
    ├── conftest.py
    ├── test_items.py
    └── test_users.py
```

## models/item.py

```python
import msgspec


class ItemCreate(msgspec.Struct):
    name: str
    price: float
    description: str = ""


class Item(msgspec.Struct):
    id: int
    name: str
    price: float
    description: str
```

## dependencies.py

```python
from FasterAPI import Header, HTTPException, Depends


async def get_current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user_id": 1}  # validate token in production


async def require_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
```

## routers/items.py

```python
from FasterAPI import FasterRouter, HTTPException, Depends, Path
from models.item import Item, ItemCreate
from dependencies import get_current_user

router = FasterRouter()

_db: dict[int, Item] = {}
_next_id = 1


@router.get("/", tags=["items"])
async def list_items():
    return list(_db.values())


@router.post("/", status_code=201, tags=["items"])
async def create_item(
    body: ItemCreate,
    user: dict = Depends(get_current_user),
):
    global _next_id
    item = Item(id=_next_id, name=body.name, price=body.price, description=body.description)
    _db[_next_id] = item
    _next_id += 1
    return item


@router.get("/{item_id}", tags=["items"])
async def get_item(item_id: int = Path()):
    if item_id not in _db:
        raise HTTPException(status_code=404, detail="Item not found")
    return _db[item_id]


@router.delete("/{item_id}", status_code=204, tags=["items"])
async def delete_item(
    item_id: int = Path(),
    user: dict = Depends(get_current_user),
):
    if item_id not in _db:
        raise HTTPException(status_code=404, detail="Item not found")
    del _db[item_id]
```

## main.py

```python
from FasterAPI import Faster
from routers.items import router as items_router
from routers.users import router as users_router
from routers.auth import router as auth_router

app = Faster(
    title="My API",
    description="Production-ready multi-router API",
    version="1.0.0",
)

app.include_router(auth_router,  prefix="/auth")
app.include_router(items_router, prefix="/items")
app.include_router(users_router, prefix="/users")
```

## Shared dependencies per router

Apply a dependency to **all routes in a router** by passing it to `include_router`:

```python
from dependencies import require_admin

# All /admin routes require admin access
app.include_router(admin_router, prefix="/admin", tags=["admin"])

# individual routes still declare Depends(require_admin) explicitly
# (router-level dependency injection is not yet a built-in feature)
```

## Configuration

```python
# config.py
import os
import msgspec


class Config(msgspec.Struct):
    db_url: str
    secret_key: str
    debug: bool = False


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config(
            db_url=os.environ["DATABASE_URL"],
            secret_key=os.environ["SECRET_KEY"],
            debug=os.environ.get("DEBUG", "false").lower() == "true",
        )
    return _config
```

## Testing big apps

```python
# tests/conftest.py
import pytest
from FasterAPI import TestClient
from main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
```

## Next steps

- [Sub-applications](sub-applications.md) — `FasterRouter` details.
- [Settings & Environment Variables](settings.md) — configuration management.
- [Testing with Overrides](testing-overrides.md) — swap deps per test.
