# Migrating from FastAPI

FasterAPI is **not** a line-for-line fork of FastAPI, but many concepts map directly.
Plan on touching **imports**, **model types**, and any code that assumed **Pydantic** or
**Starlette** internals.

## 1. Install and import

| FastAPI | FasterAPI |
|--------|-----------|
| `pip install fastapi` | `pip install faster-api-web` |
| `from fastapi import FastAPI` | `from FasterAPI import Faster` |
| `app = FastAPI()` | `app = Faster()` |

The PyPI distribution name is **`faster-api-web`**. The Python package directory is **`FasterAPI`**
(capital **F** and **API**).

## 2. Replace Pydantic models with msgspec

Validation and JSON encoding use **msgspec** structs:

```python
# FastAPI
from pydantic import BaseModel

class User(BaseModel):
    name: str
    email: str
```

```python
# FasterAPI
import msgspec

class User(msgspec.Struct):
    name: str
    email: str
```

**Field defaults**, **optional** fields, and **nested** structs work with msgspec’s usual rules.
If you relied on Pydantic-specific validators (`@field_validator`) or complex JSON Schema,
reimplement that logic with plain Python or narrow msgspec types.

## 3. Routing and decorators

`@app.get`, `@app.post`, `APIRouter`-style grouping, path parameters, and `Depends()` are
intended to feel familiar. Differences tend to be **edge cases** (custom Starlette routes,
advanced middleware ordering). Port routes one module at a time and run tests.

## 4. Exceptions and responses

`HTTPException`, JSON responses, redirects, and file responses have near-equivalent types
under `FasterAPI`. Check response **headers** and **status codes** in integration tests after
migration.

## 5. OpenAPI and docs

OpenAPI generation is supported; field metadata may differ slightly from Pydantic’s schema
extras. Regenerate your client or inspect `/openapi.json` after switching models.

## 6. Testing

Use **`TestClient`** from **`FasterAPI`** (httpx-based), similar to Starlette’s test client.
Install **`httpx`** in the environment where you run tests (`pip install httpx` — it is included in
the project’s **dev** extras but not in the minimal runtime install). Update imports and rerun your
suite; fix any tests that imported Starlette types directly.

## Suggested order of work

1. Add **FasterAPI** beside FastAPI in a branch; swap the app factory and deps.
2. Convert **models** to `msgspec.Struct` and fix type errors.
3. Run **tests** and fix request/response assumptions.
4. Measure **latency/throughput** in staging if performance is a goal.

If something you need is missing, open an issue with a minimal reproduction against
the [GitHub repo](https://github.com/FasterApiWeb/FasterAPI).
