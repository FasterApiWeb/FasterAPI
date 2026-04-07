# FasterAPI

[![PyPI version](https://img.shields.io/pypi/v/faster-api.svg)](https://pypi.org/project/faster-api/)
[![CI](https://github.com/EshwarCVS/FasterAPI/actions/workflows/ci.yml/badge.svg)](https://github.com/EshwarCVS/FasterAPI/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**FasterAPI** is a high-performance ASGI web framework for Python 3.11+.
It keeps the developer experience you know from FastAPI while replacing
the internals with faster components: **msgspec** instead of Pydantic,
a **radix-tree router** instead of regex matching, and **uvloop** as the
default event loop.

If you already know FastAPI, you already know FasterAPI.

---

## Why FasterAPI?

| Feature | FasterAPI | FastAPI |
|---|---|---|
| **Validation / Serialisation** | msgspec Struct (compiled) | Pydantic BaseModel |
| **Routing** | Radix tree (~6x faster lookups) | Regex-based (Starlette) |
| **Event loop** | uvloop (auto-installed) | stdlib asyncio |
| **JSON encoding** | msgspec.json (C extension) | stdlib json / orjson opt-in |
| **Dependency injection** | Built-in, same `Depends()` API | Built-in `Depends()` |
| **OpenAPI docs** | Auto-generated, Swagger + ReDoc | Auto-generated, Swagger + ReDoc |
| **WebSocket** | Built-in | Built-in (via Starlette) |
| **Middleware** | CORS, GZip, TrustedHost, HTTPS | CORS, GZip, TrustedHost, HTTPS |
| **Background tasks** | Built-in `BackgroundTasks` | Built-in `BackgroundTasks` |
| **Test client** | Built-in `TestClient` (httpx) | Via Starlette `TestClient` |
| **Python version** | 3.11+ | 3.8+ |

---

## Installation

```bash
pip install faster-api
```

Or install from source:

```bash
git clone https://github.com/EshwarCVS/FasterAPI.git
cd FasterAPI
pip install -e ".[dev]"
```

---

## Quick Start

```python
import msgspec
from FasterAPI import Faster, Path

app = Faster()

class Item(msgspec.Struct):
    name: str
    price: float

@app.get("/items/{item_id}")
async def get_item(item_id: str = Path()):
    return {"item_id": item_id}

@app.post("/items", status_code=201)
async def create_item(item: Item):
    return {"name": item.name, "price": item.price}
```

```bash
uvicorn app:app --reload
```

Open http://localhost:8000/docs for Swagger UI.

---

## Full Example

The example below demonstrates routing, validation, dependency injection,
background tasks, middleware, and WebSocket support in a single file.

```python
import msgspec
from FasterAPI import (
    BackgroundTasks,
    CORSMiddleware,
    Depends,
    Faster,
    FasterRouter,
    HTTPException,
    Path,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)

app = Faster(title="My API", version="1.0.0")

# ── Middleware ──
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])

# ── Models ──
class User(msgspec.Struct):
    name: str
    email: str

# ── In-memory store ──
db: dict[str, dict] = {}

# ── Dependencies ──
async def get_db():
    return db

# ── Router ──
router = FasterRouter(prefix="/users", tags=["users"])

@router.get("", summary="List users")
async def list_users(
    skip: str = Query("0"),
    limit: str = Query("20"),
    store: dict = Depends(get_db),
):
    users = list(store.values())
    return users[int(skip):int(skip) + int(limit)]

@router.post("", summary="Create user", status_code=status.HTTP_201_CREATED)
async def create_user(body: User, bg: BackgroundTasks, store: dict = Depends(get_db)):
    user_id = str(len(store) + 1)
    store[user_id] = {"id": user_id, "name": body.name, "email": body.email}
    bg.add_task(print, f"Created user {user_id}")
    return store[user_id]

@router.get("/{user_id}", summary="Get user")
async def get_user(user_id: str = Path(), store: dict = Depends(get_db)):
    if user_id not in store:
        raise HTTPException(status_code=404, detail="User not found")
    return store[user_id]

@router.delete("/{user_id}", summary="Delete user")
async def delete_user(user_id: str = Path(), store: dict = Depends(get_db)):
    if user_id not in store:
        raise HTTPException(status_code=404, detail="User not found")
    return {"deleted": store.pop(user_id)["id"]}

app.include_router(router)

# ── WebSocket ──
@app.websocket("/ws")
async def ws_echo(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            text = await ws.receive_text()
            await ws.send_text(f"echo: {text}")
    except WebSocketDisconnect:
        pass
```

---

## Benchmarks

Measured with `httpx.AsyncClient`, 10 000 requests at 100 concurrency.
Both frameworks running under `uvicorn` on the same machine.

| Endpoint | FasterAPI (req/s) | FastAPI (req/s) | Speedup |
|---|---|---|---|
| `GET /health` | _TBD_ | _TBD_ | _TBD_ |
| `GET /users/{id}` | _TBD_ | _TBD_ | _TBD_ |
| `POST /users` | _TBD_ | _TBD_ | _TBD_ |

**Routing micro-benchmark** (100 routes, 1M lookups):

| Router | Ops/s |
|---|---|
| Radix tree (FasterAPI) | ~800 000 |
| Regex (traditional) | ~120 000 |

Run benchmarks yourself:

```bash
python benchmarks/compare.py              # HTTP head-to-head
python benchmarks/profile_routing.py      # Routing profiler
```

---

## Migration Guide from FastAPI

FasterAPI is designed as a drop-in replacement. Most code migrates with
a find-and-replace.

### What changes

| FastAPI | FasterAPI | Notes |
|---|---|---|
| `from fastapi import FastAPI` | `from FasterAPI import Faster` | App class renamed |
| `app = FastAPI()` | `app = Faster()` | Same constructor kwargs |
| `class Item(BaseModel):` | `class Item(msgspec.Struct):` | msgspec instead of Pydantic |
| `from fastapi import APIRouter` | `from FasterAPI import FasterRouter` | Router renamed |
| `from starlette.testclient import TestClient` | `from FasterAPI import TestClient` | Built-in |
| `from starlette.status import ...` | `from FasterAPI import status` | `status.HTTP_200_OK` etc. |

### What stays identical

These APIs work exactly the same way -- no changes needed:

- **Decorators**: `@app.get()`, `@app.post()`, `@app.put()`, `@app.delete()`, `@app.patch()`
- **Dependency injection**: `Depends()`, `use_cache`, nested dependencies
- **Parameter descriptors**: `Path()`, `Query()`, `Header()`, `Cookie()`, `Body()`, `File()`, `Form()`
- **Middleware**: `app.add_middleware(CORSMiddleware, ...)`, same kwargs
- **Exception handling**: `HTTPException`, `RequestValidationError`, `app.add_exception_handler()`
- **Background tasks**: `BackgroundTasks` injection, `bg.add_task()`
- **WebSocket**: `@app.websocket()`, `await ws.accept()`, send/receive
- **Lifecycle hooks**: `@app.on_startup`, `@app.on_shutdown`
- **OpenAPI**: Auto-generated at `/openapi.json`, Swagger at `/docs`, ReDoc at `/redoc`
- **Response classes**: `JSONResponse`, `HTMLResponse`, `PlainTextResponse`, `RedirectResponse`, `StreamingResponse`, `FileResponse`
- **Router inclusion**: `app.include_router(router, prefix=..., tags=...)`

### Example migration

**Before (FastAPI):**

```python
from fastapi import FastAPI, Depends, HTTPException, Query
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

@app.post("/items")
async def create(item: Item):
    return item
```

**After (FasterAPI):**

```python
import msgspec
from FasterAPI import Faster, Depends, HTTPException, Query

app = Faster()

class Item(msgspec.Struct):
    name: str
    price: float

@app.post("/items")
async def create(item: Item):
    return {"name": item.name, "price": item.price}
```

---

## Project Structure

```
FasterAPI/
    __init__.py          # Public API exports
    app.py               # Faster application class (ASGI)
    router.py            # RadixRouter + FasterRouter
    request.py           # Request object
    response.py          # Response classes
    params.py            # Path, Query, Body, Header, Cookie, File, Form
    dependencies.py      # Depends + DI resolver
    exceptions.py        # HTTPException, RequestValidationError
    middleware.py         # CORS, GZip, TrustedHost, HTTPS redirect
    background.py        # BackgroundTask, BackgroundTasks
    websocket.py         # WebSocket, WebSocketDisconnect
    datastructures.py    # UploadFile, FormData
    concurrency.py       # Thread/process pool utilities
    testclient.py        # TestClient (httpx-based)
    status.py            # HTTP status code constants
    openapi/
        __init__.py
        generator.py     # OpenAPI 3.0.3 spec generation
        ui.py            # Swagger UI + ReDoc HTML
tests/
    test_routing.py
    test_params.py
    test_deps.py
    test_responses.py
    test_exceptions.py
    test_openapi.py
    test_middleware.py
    test_websocket.py
    test_background.py
    test_formdata.py
    test_integration.py
    test_benchmark.py
examples/
    basic_app.py         # Minimal hello world
    full_crud_app.py     # Complete CRUD with all features
    websocket_app.py     # WebSocket chat room
benchmarks/
    compare.py           # FasterAPI vs FastAPI head-to-head
    profile_routing.py   # Radix tree vs regex profiler
    README.md
```

---

## Contributing

Contributions are welcome.

```bash
# Clone and install
git clone https://github.com/EshwarCVS/FasterAPI.git
cd FasterAPI
pip install -e ".[dev]"

# Run tests
pytest

# Run benchmarks
python benchmarks/compare.py
python benchmarks/profile_routing.py
```

Please ensure all tests pass before submitting a pull request.

---

## License

[MIT](LICENSE) -- Eshwar Chandra Vidhyasagar Thedla
