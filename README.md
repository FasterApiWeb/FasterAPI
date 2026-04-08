# FasterAPI

[![PyPI version](https://img.shields.io/pypi/v/faster-api.svg)](https://pypi.org/project/faster-api/)
[![CI](https://github.com/EshwarCVS/FasterAPI/actions/workflows/ci.yml/badge.svg)](https://github.com/EshwarCVS/FasterAPI/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**FasterAPI** is a high-performance ASGI web framework for Python 3.11+.
It keeps the developer experience you know from FastAPI while replacing
the internals with faster components: **msgspec** instead of Pydantic,
a **radix-tree router** instead of regex matching, **uvloop** as the
default event loop, and **Python 3.13 sub-interpreters** for true
CPU-bound parallelism.

If you already know FastAPI, you already know FasterAPI.

---

## Why FasterAPI?

FastAPI is excellent, but it carries inherited overhead from Pydantic
(pure-Python validation) and Starlette (regex-based routing). FasterAPI
swaps those internals for compiled alternatives while keeping an
identical developer-facing API:

- **msgspec Structs** replace Pydantic BaseModel. msgspec validates and
  serialises data through a C extension — typically 5-20x faster than
  Pydantic v2 for JSON encoding.
- **Radix-tree routing** replaces regex-based path matching. Route
  lookups run in O(k) time (k = path length) regardless of how many
  routes are registered. With 100 routes, this delivers ~6.5x faster
  lookups than regex (see benchmarks below).
- **uvloop** replaces the stdlib asyncio event loop by default, cutting
  event-loop overhead by 2-3x on Linux.
- **Python 3.13 sub-interpreters** (PEP 684 / PEP 734) give each worker
  its own GIL — the closest Python analog to Go's goroutines. On
  Python < 3.13, FasterAPI transparently falls back to
  `ProcessPoolExecutor`.

| Feature | FasterAPI | FastAPI |
|---|---|---|
| **Validation / Serialisation** | msgspec Struct (C extension) | Pydantic BaseModel |
| **Routing** | Radix tree (O(k) lookup, ~6.5x faster) | Regex-based (Starlette) |
| **Event loop** | uvloop (auto-installed) | stdlib asyncio |
| **JSON encoding** | msgspec.json (C extension) | stdlib json / orjson opt-in |
| **CPU parallelism** | Sub-interpreters (3.13+) | N/A |
| **Dependency injection** | Built-in, same `Depends()` API | Built-in `Depends()` |
| **OpenAPI docs** | Auto-generated, Swagger + ReDoc | Auto-generated, Swagger + ReDoc |
| **WebSocket** | Built-in | Built-in (via Starlette) |
| **Middleware** | CORS, GZip, TrustedHost, HTTPS | CORS, GZip, TrustedHost, HTTPS |
| **Background tasks** | Built-in `BackgroundTasks` | Built-in `BackgroundTasks` |
| **Test client** | Built-in `TestClient` (httpx) | Via Starlette `TestClient` |
| **Python version** | 3.11+ (3.13+ for sub-interpreters) | 3.8+ |

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

### Requirements

- **Python 3.11+** (3.13+ recommended for sub-interpreter support)
- **uvloop** — installed automatically; provides the fast event loop
- **msgspec** — installed automatically; used for validation & JSON
- **uvicorn** — installed automatically; ASGI server
- **python-multipart** — installed automatically; for file uploads and form data

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

Open http://localhost:8000/docs for interactive Swagger UI documentation.
Open http://localhost:8000/redoc for ReDoc documentation.

---

## Core Concepts

### Models with msgspec

FasterAPI uses `msgspec.Struct` instead of Pydantic's `BaseModel`. Structs
compile to efficient C code at import time, so validation and serialisation
are significantly faster:

```python
import msgspec

class User(msgspec.Struct):
    name: str
    email: str
    age: int = 0                # default value
    tags: list[str] = []        # default factory
```

`msgspec.Struct` supports all the type annotations you'd use with Pydantic
— `str`, `int`, `float`, `bool`, `list[T]`, `dict[K, V]`, `Optional[T]`,
nested structs, etc.

### Dependency Injection

FasterAPI's `Depends()` works exactly like FastAPI's — declare a callable
and FasterAPI will resolve it (and its sub-dependencies) automatically:

```python
from FasterAPI import Depends, Faster

app = Faster()

async def get_db():
    # In a real app, return a DB session
    return {"connected": True}

@app.get("/status")
async def status(db: dict = Depends(get_db)):
    return db
```

Dependencies are cached per-request by default. Use `Depends(fn, use_cache=False)`
to disable caching.

### Parameter Descriptors

Extract data from different parts of the request using descriptors:

```python
from FasterAPI import Faster, Path, Query, Header, Cookie, Body

app = Faster()

@app.get("/items/{item_id}")
async def get_item(
    item_id: str = Path(description="The item ID"),
    q: str = Query("default", description="Search query"),
    x_token: str = Header(None, alias="x-token"),
    session: str = Cookie(None),
):
    return {"item_id": item_id, "q": q}
```

### Background Tasks

Run work after the response is sent — logging, sending emails, etc.:

```python
from FasterAPI import BackgroundTasks, Faster

app = Faster()

def send_email(to: str, subject: str):
    print(f"Sending '{subject}' to {to}")

@app.post("/notify")
async def notify(bg: BackgroundTasks):
    bg.add_task(send_email, "user@example.com", "Welcome!")
    return {"status": "queued"}
```

### WebSocket

```python
from FasterAPI import Faster, WebSocket, WebSocketDisconnect

app = Faster()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_text()
            await ws.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        print("Client disconnected")
```

### Sub-Interpreters (Python 3.13+)

For CPU-bound work, FasterAPI provides sub-interpreter support. Each
sub-interpreter runs with its own GIL, enabling true parallelism without
process overhead:

```python
from FasterAPI import Faster, run_in_subinterpreter

app = Faster()

def heavy_computation(n: int) -> int:
    return sum(i * i for i in range(n))

@app.get("/compute/{n}")
async def compute(n: int):
    # Runs in a sub-interpreter with its own GIL (3.13+)
    # Falls back to ProcessPoolExecutor on older Python
    result = await run_in_subinterpreter(heavy_computation, n)
    return {"result": result}
```

### Middleware

```python
from FasterAPI import CORSMiddleware, Faster, GZipMiddleware

app = Faster()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

Available middleware: `CORSMiddleware`, `GZipMiddleware`,
`TrustedHostMiddleware`, `HTTPSRedirectMiddleware`, `BaseHTTPMiddleware`.

### Router

Group routes under a common prefix and set of tags:

```python
from FasterAPI import Faster, FasterRouter

router = FasterRouter(prefix="/api/v1", tags=["v1"])

@router.get("/items")
async def list_items():
    return []

app = Faster()
app.include_router(router)
# Route is registered as GET /api/v1/items
```

---

## Full Example

The example below demonstrates routing, validation, dependency injection,
background tasks, middleware, and WebSocket support in a single file:

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

Run with:

```bash
uvicorn examples.full_crud_app:app --reload
```

---

## Benchmarks

### Routing Micro-Benchmark

100 routes (static + parameterized), 1,000,000 lookups:

| Router | Ops/s | Speedup |
|---|---|---|
| **Radix tree (FasterAPI)** | **~767,000** | **6.5x** |
| Regex (traditional) | ~118,000 | 1.0x |

The radix tree performs O(k) lookups (k = path segment count), while
regex routers scan routes linearly. The gap widens as route count grows.

### HTTP End-to-End Benchmark

Measured with `httpx.AsyncClient`, 10,000 requests at 100 concurrency.
Both frameworks under `uvicorn` on the same machine:

| Endpoint | FasterAPI (req/s) | FastAPI (req/s) | Notes |
|---|---|---|---|
| `GET /health` | ~370 | ~410 | Simple JSON, I/O-bound |
| `GET /users/{id}` | ~415 | ~490 | Path param extraction |
| `POST /users` | ~335 | ~335 | JSON body parse + validate |

**Note:** End-to-end HTTP benchmarks are dominated by network and event
loop overhead rather than framework code. FasterAPI's core advantages —
faster routing, faster JSON serialisation, and faster validation — show
up most clearly in:

1. **Routing-heavy applications** with many registered routes
2. **JSON-heavy workloads** where msgspec's C-based encoder/decoder
   outperforms stdlib json by 5-20x
3. **Validation-heavy endpoints** where msgspec Struct validation
   compiles to C code vs Pydantic's Python-layer validation
4. **CPU-bound handlers** using sub-interpreters (Python 3.13+) for
   true parallelism without process overhead

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

### Step-by-step migration

1. **Install FasterAPI**: `pip install faster-api`
2. **Replace imports**: `FastAPI` -> `Faster`, `APIRouter` -> `FasterRouter`
3. **Replace models**: Change `class Foo(BaseModel):` to `class Foo(msgspec.Struct):` and add `import msgspec`
4. **Update return values**: Pydantic models have `.dict()` / `.model_dump()` — msgspec Structs use `msgspec.to_builtins(obj)` or return fields directly
5. **Test**: Your existing test suite should pass with minimal changes

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

## Architecture

FasterAPI is built as a minimal ASGI framework with no external framework
dependencies (no Starlette). The key components:

```
Request → Router (radix tree) → DI Resolver → Handler → Response
              ↓                      ↓
        path params          Depends(), Body(), Query(), etc.
```

- **ASGI core** (`app.py`): Handles HTTP, WebSocket, and lifespan protocols
- **Radix router** (`router.py`): O(k) path matching with parameter extraction
- **DI resolver** (`dependencies.py`): Introspects handler signatures, resolves
  `Depends()` chains, injects parameters from path/query/headers/cookies/body
- **Concurrency** (`concurrency.py`): Thread pool, process pool, and Python 3.13+
  sub-interpreter pool with per-interpreter GIL

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
    concurrency.py       # Thread/process pool + sub-interpreter support
    testclient.py        # TestClient (httpx-based)
    status.py            # HTTP status code constants
    openapi/
        __init__.py
        generator.py     # OpenAPI 3.0.3 spec generation
        ui.py            # Swagger UI + ReDoc HTML
tests/
    test_routing.py      # Radix router tests
    test_params.py       # Parameter descriptor tests
    test_deps.py         # Dependency injection tests
    test_responses.py    # Response class tests
    test_exceptions.py   # Exception handling tests
    test_openapi.py      # OpenAPI generation tests
    test_middleware.py    # Middleware tests
    test_websocket.py    # WebSocket tests
    test_background.py   # Background task tests
    test_formdata.py     # File upload / form data tests
    test_integration.py  # Full CRUD integration tests
    test_benchmark.py    # Performance regression tests
examples/
    basic_app.py         # Minimal hello world
    full_crud_app.py     # Complete CRUD with all features
    websocket_app.py     # WebSocket chat room
benchmarks/
    compare.py           # FasterAPI vs FastAPI head-to-head
    profile_routing.py   # Radix tree vs regex profiler
    README.md            # Benchmark methodology and results
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

# Type check
mypy FasterAPI/

# Run benchmarks
python benchmarks/compare.py
python benchmarks/profile_routing.py
```

Please ensure all tests pass and mypy reports no errors before submitting
a pull request.

---

## License

[MIT](LICENSE) -- Eshwar Chandra Vidhyasagar Thedla
