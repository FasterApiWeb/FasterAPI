# Sub-applications

FasterAPI's `include_router` lets you split your API across multiple files and
routers, each mounted under a shared prefix.

## Basic router

```python
# items/router.py
from FasterAPI import FasterRouter, HTTPException
import msgspec

router = FasterRouter()

_items: dict[int, dict] = {}


class Item(msgspec.Struct):
    name: str
    price: float


@router.get("/", tags=["items"])
async def list_items():
    return list(_items.values())


@router.post("/", status_code=201, tags=["items"])
async def create_item(item: Item):
    new_id = len(_items) + 1
    _items[new_id] = {"id": new_id, **msgspec.structs.asdict(item)}
    return _items[new_id]


@router.get("/{item_id}", tags=["items"])
async def get_item(item_id: int):
    if item_id not in _items:
        raise HTTPException(status_code=404, detail="Not found")
    return _items[item_id]
```

```python
# main.py
from FasterAPI import Faster
from items.router import router as items_router
from users.router import router as users_router

app = Faster(title="Multi-router API")

app.include_router(items_router, prefix="/items")
app.include_router(users_router, prefix="/users", tags=["users"])
```

## Router with prefix and tags

All routes registered through the router inherit the `prefix` and `tags` passed to
`include_router`:

```python
# The router's @router.get("/") becomes GET /items/
# @router.get("/{item_id}") becomes GET /items/{item_id}
app.include_router(items_router, prefix="/items", tags=["items"])
```

## Multiple versions

```python
from v1.router import router as v1_router
from v2.router import router as v2_router

app.include_router(v1_router, prefix="/v1")
app.include_router(v2_router, prefix="/v2")
```

## Nested routers

```python
# admin/users.py
admin_users_router = FasterRouter()

# admin/__init__.py
from FasterAPI import FasterRouter
from .users import admin_users_router

admin_router = FasterRouter()
# Include nested router — FasterRouter.include_router mirrors app.include_router
```

Currently `FasterRouter` does not expose `include_router` directly; nest via
`app.include_router` with different prefixes:

```python
app.include_router(admin_users_router, prefix="/admin/users", tags=["admin"])
app.include_router(admin_settings_router, prefix="/admin/settings", tags=["admin"])
```

## Recommended project layout

```
myproject/
├── main.py               # create Faster() app, include_router calls
├── dependencies.py       # shared Depends() callables
├── models.py             # shared msgspec.Struct definitions
├── items/
│   ├── __init__.py
│   ├── router.py         # FasterRouter with /items routes
│   └── models.py
├── users/
│   ├── __init__.py
│   ├── router.py
│   └── models.py
└── auth/
    ├── __init__.py
    └── router.py
```

See [Bigger Applications](bigger-apps.md) for a fully-worked example.

## ASGI sub-applications

Mount a completely separate ASGI app (e.g. another FasterAPI instance or a
third-party ASGI app) by routing a prefix manually:

```python
admin_app = Faster(title="Admin API", docs_url="/docs")

# Dispatch /admin/* to admin_app
@app.get("/admin/{rest_of_path:path}")
async def admin_proxy(rest_of_path: str, request: Request):
    # adjust scope and dispatch
    ...
```

For full ASGI mounting, wrap at the ASGI level outside FasterAPI using a helper like
`a2wsgi` or write a custom router.

## Next steps

- [Bigger Applications](bigger-apps.md) — end-to-end multi-file project.
- [Metadata & Docs](../tutorial/metadata.md) — tags and route descriptions at scale.
