# Metadata & Docs

FasterAPI auto-generates an OpenAPI schema and serves Swagger UI and ReDoc. You can
customise every aspect — app-level metadata, per-route tags, summaries, and more.

## Application metadata

```python
from FasterAPI import Faster

app = Faster(
    title="My Inventory API",
    description="Manage items, orders, and users.",
    version="2.1.0",
    docs_url="/docs",      # Swagger UI (default)
    redoc_url="/redoc",    # ReDoc (default)
    openapi_url="/openapi.json",
)
```

Visit `http://localhost:8000/docs` for the interactive Swagger UI.

## Disable docs

Set `docs_url=None` and / or `redoc_url=None`:

```python
app = Faster(docs_url=None, redoc_url=None)
```

To disable OpenAPI entirely (no schema endpoint):

```python
app = Faster(openapi_url=None)
```

## Route tags

Group routes in the Swagger UI sidebar with `tags`:

```python
@app.get("/items", tags=["items"])
async def list_items():
    return []


@app.post("/items", tags=["items"])
async def create_item():
    return {}


@app.get("/users", tags=["users"])
async def list_users():
    return []
```

## Summary and description

```python
@app.get(
    "/items/{item_id}",
    summary="Retrieve a single item",
    tags=["items"],
)
async def get_item(item_id: int):
    """Return the item identified by *item_id*.

    Raises 404 if the item does not exist.
    """
    return {"item_id": item_id}
```

The docstring appears as the route's **description** in the OpenAPI schema.

## Deprecated routes

Mark old endpoints without removing them:

```python
@app.get("/old-endpoint", deprecated=True)
async def old_endpoint():
    return {"moved": "/new-endpoint"}
```

## Custom response status code

```python
@app.post("/items", status_code=201, tags=["items"])
async def create_item():
    return {}
```

## Using routers for organisation

Group related routes in a `FasterRouter`:

```python
from FasterAPI import Faster, FasterRouter

app = Faster()
router = FasterRouter()


@router.get("/", tags=["items"])
async def list_items():
    return []


@router.post("/", tags=["items"], status_code=201)
async def create_item():
    return {}


app.include_router(router, prefix="/items")
```

All routes from the router are mounted under `/items` and inherit the provided tags.

## Next steps

- [Advanced: OpenAPI Customisation](../advanced/openapi-customization.md) — extend or
  conditionally show the schema.
- [Advanced: Bigger Applications](../advanced/bigger-apps.md) — split routes across
  multiple files.
