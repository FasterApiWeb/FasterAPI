# Migrating from FastAPI

FasterAPI is **not** a line-for-line fork of FastAPI, but many concepts map directly.
Plan on touching **imports**, **model types**, and any code that assumed **Pydantic** or
**Starlette** internals.

## Quick reference

| FastAPI | FasterAPI |
|--------|-----------|
| `pip install fastapi` | `pip install faster-api-web` |
| `from fastapi import FastAPI` | `from FasterAPI import Faster` |
| `app = FastAPI()` | `app = Faster()` |
| `from fastapi import APIRouter` | `from FasterAPI import FasterRouter` |
| `from fastapi.testclient import TestClient` | `from FasterAPI import TestClient` |
| `from pydantic import BaseModel` | `import msgspec; class M(msgspec.Struct)` |
| `from starlette.requests import Request` | `from FasterAPI import Request` |
| `from fastapi.responses import JSONResponse` | `from FasterAPI import JSONResponse` |

The PyPI distribution name is **`faster-api-web`**. The Python package directory is
**`FasterAPI`** (capital **F** and **API**).

## 1. Replace Pydantic models with msgspec

Validation and JSON encoding use **msgspec** structs:

```python
# FastAPI
from pydantic import BaseModel

class User(BaseModel):
    name: str
    email: str
    age: int | None = None
```

```python
# FasterAPI
import msgspec

class User(msgspec.Struct):
    name: str
    email: str
    age: int | None = None
```

**Field defaults**, **optional** fields, and **nested** structs work with msgspec's
usual rules.

### Pydantic-specific features and equivalents

| Pydantic | msgspec equivalent |
|---|---|
| `@field_validator` | Plain function validation before/after constructing the struct |
| `model_config = ConfigDict(...)` | `msgspec.Struct`'s class kwargs (e.g. `frozen=True`) |
| `model.model_dump()` | `msgspec.structs.asdict(model)` |
| `model.model_dump_json()` | `msgspec.json.encode(model)` |
| `Model.model_validate(data)` | `msgspec.json.decode(data, type=Model)` |
| `Field(ge=0, le=100)` | `msgspec.Meta(ge=0, le=100)` with `Annotated` |
| `@computed_field` | Regular `@property` (not in OpenAPI schema) |

### Annotated constraints

```python
from typing import Annotated
import msgspec

Price = Annotated[float, msgspec.Meta(ge=0)]
Name  = Annotated[str,   msgspec.Meta(min_length=1, max_length=100)]


class Product(msgspec.Struct):
    name: Name
    price: Price
```

## 2. Routing and decorators

`@app.get`, `@app.post`, `@app.put`, `@app.delete`, `@app.patch`, `@app.websocket`,
`APIRouter`-style grouping, path parameters, and `Depends()` are designed to feel
familiar.

```python
# FastAPI
from fastapi import APIRouter
router = APIRouter()

# FasterAPI
from FasterAPI import FasterRouter
router = FasterRouter()
```

`include_router` works the same:

```python
app.include_router(router, prefix="/items", tags=["items"])
```

## 3. Exceptions and responses

`HTTPException`, JSON responses, redirects, and file responses have near-equivalent
types under `FasterAPI`. Differences:

- `HTTPException.headers` is a `dict[str, str]` in both frameworks.
- `RequestValidationError.errors` is a list of dicts (same structure).
- `Response` subclasses accept `headers: dict[str, str]` (same as FastAPI).

```python
# Same in both
raise HTTPException(status_code=404, detail="Not found")
raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Bearer"})
```

## 4. OpenAPI and docs

OpenAPI generation is supported; field metadata may differ slightly from Pydantic's
schema extras. Regenerate your client or inspect `/openapi.json` after switching.

```python
# Both support the same constructor arguments
app = Faster(
    title="My API",
    description="...",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
```

## 5. Testing

Use **`TestClient`** from **`FasterAPI`** (httpx-based), similar to FastAPI's test
client:

```python
# FastAPI
from fastapi.testclient import TestClient

# FasterAPI
from FasterAPI import TestClient  # requires: pip install httpx
```

## 6. Background tasks

```python
# FastAPI
from fastapi import BackgroundTasks

# FasterAPI
from FasterAPI import BackgroundTasks
```

Usage is identical — declare `BackgroundTasks` as a parameter:

```python
@app.post("/items")
async def create(tasks: BackgroundTasks):
    tasks.add_task(send_email, "user@example.com")
    return {"status": "queued"}
```

## 7. Middleware

```python
# FastAPI (via Starlette)
from starlette.middleware.cors import CORSMiddleware

# FasterAPI
from FasterAPI import CORSMiddleware

app.add_middleware(CORSMiddleware, allow_origins=["*"])
```

## 8. WebSockets

```python
# FastAPI
from fastapi import WebSocket

# FasterAPI
from FasterAPI import WebSocket
```

## Common migration gotchas

### `Annotated` parameters

FastAPI uses `Annotated[int, Path(ge=1)]`; FasterAPI uses `int = Path()`.

```python
# FastAPI style
async def get(item_id: Annotated[int, Path(ge=1)]): ...

# FasterAPI style
async def get(item_id: int = Path()): ...
```

### `response_model` is not yet fully supported

FasterAPI uses the return type annotation for response serialisation.  If you relied
on `response_model=` for filtering fields, use a separate response struct:

```python
# FastAPI
@app.get("/users/{id}", response_model=UserPublic)
async def get_user(id: int) -> UserFull: ...

# FasterAPI — return the right type directly
@app.get("/users/{id}")
async def get_user(id: int) -> UserPublic:
    full = await fetch_user(id)
    return UserPublic(id=full.id, name=full.name)
```

### Starlette-specific imports

Any code that imported directly from `starlette.*` needs updating to equivalent
FasterAPI imports or plain Python/httpx alternatives.

## Suggested migration order

1. Add **FasterAPI** beside FastAPI in a branch; swap the app factory.
2. Convert **models** to `msgspec.Struct` and fix type errors.
3. Run **tests** and fix request/response assumptions.
4. Measure **latency/throughput** in staging if performance is a goal.
5. Remove FastAPI / Pydantic / Starlette from dependencies.

## Real-world case studies

### Simple CRUD service

A typical CRUD API with 10–20 routes, PostgreSQL backend, and simple token auth
typically migrates in **2–4 hours**:

- 30 min: swap imports and app constructor
- 1–2 hours: convert Pydantic models to msgspec structs
- 30 min: fix test imports and re-run suite
- 30 min: verify OpenAPI output and update generated client

### Performance gains observed

On equivalent hardware, teams have reported:

- **2–3×** improvement in JSON serialisation throughput (msgspec vs Pydantic)
- **10–20%** lower p99 latency under load (radix router + uvloop)
- Smaller memory footprint (no Pydantic overhead per request)

If something you need is missing, open an issue with a minimal reproduction against
the [GitHub repo](https://github.com/FasterApiWeb/FasterAPI).
