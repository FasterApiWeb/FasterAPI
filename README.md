# FasterAPI

[![PyPI version](https://img.shields.io/pypi/v/faster-api.svg)](https://pypi.org/project/faster-api/)
[![CI](https://github.com/EshwarCVS/FasterAPI/actions/workflows/ci.yml/badge.svg)](https://github.com/EshwarCVS/FasterAPI/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**FasterAPI** is a high-performance ASGI web framework for Python,
written for **Python 3.13** first and with graceful fallbacks to 3.12,
3.11, and older.

It keeps the developer experience you know from FastAPI while replacing
the internals with faster components: **msgspec** instead of Pydantic,
a **radix-tree router** instead of regex matching, **uvloop** as the
default event loop (optional on 3.13+), and **Python 3.13
sub-interpreters** for true CPU-bound parallelism.

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
  routes are registered. With 100 routes, this delivers **~6x faster
  lookups** than regex (see benchmarks below).
- **uvloop** replaces the stdlib asyncio event loop by default, cutting
  event-loop overhead by 2-3x on Linux. On Python 3.13+, uvloop is
  optional — stdlib asyncio is already significantly faster.
- **Python 3.13 sub-interpreters** (PEP 684 / PEP 734) give each worker
  its own GIL — the closest Python analog to Go's goroutines. On
  Python < 3.13, FasterAPI transparently falls back to
  `ProcessPoolExecutor`.

| Feature | FasterAPI | FastAPI |
|---|---|---|
| **Validation / Serialisation** | msgspec Struct (C extension) | Pydantic BaseModel |
| **Routing** | Radix tree (O(k) lookup, ~6x faster) | Regex-based (Starlette) |
| **Event loop** | uvloop (auto) / stdlib on 3.13+ | stdlib asyncio |
| **JSON encoding** | msgspec.json (C extension) | stdlib json / orjson opt-in |
| **CPU parallelism** | Sub-interpreters (3.13+) / ProcessPool (3.11+) | N/A |
| **Dependency injection** | Built-in, same `Depends()` API | Built-in `Depends()` |
| **OpenAPI docs** | Auto-generated, Swagger + ReDoc | Auto-generated, Swagger + ReDoc |
| **WebSocket** | Built-in | Built-in (via Starlette) |
| **Middleware** | CORS, GZip, TrustedHost, HTTPS | CORS, GZip, TrustedHost, HTTPS |
| **Background tasks** | Built-in `BackgroundTasks` | Built-in `BackgroundTasks` |
| **Test client** | Built-in `TestClient` (httpx) | Via Starlette `TestClient` |
| **Python version** | 3.13 first, 3.11+ supported | 3.8+ |

---

## Installation

```bash
pip install faster-api
```

For maximum performance (includes uvloop):

```bash
pip install faster-api[all]
```

Or install from source:

```bash
git clone https://github.com/EshwarCVS/FasterAPI.git
cd FasterAPI
pip install -e ".[dev]"
```

### Requirements

- **Python 3.13** (recommended) — full sub-interpreter support, faster asyncio
- **Python 3.12** — partial per-interpreter GIL support, ProcessPool fallback
- **Python 3.11** — minimum supported version, ProcessPool fallback
- **uvloop** — optional; auto-detected at startup. If not installed,
  stdlib asyncio is used (fast enough on 3.13+)
- **msgspec** — required; used for validation & JSON encoding
- **uvicorn** — required; ASGI server
- **python-multipart** — required; for file uploads and form data

### Python Version Compatibility

| Feature | 3.13+ | 3.12 | 3.11 |
|---|---|---|---|
| Sub-interpreters (own GIL) | Native | ProcessPool fallback | ProcessPool fallback |
| asyncio performance | Excellent (PEP 703 prep) | Good | Good |
| uvloop benefit | Optional (~10-15% faster) | Recommended (~2-3x faster) | Recommended (~2-3x faster) |
| Type syntax (`X \| Y`) | Native | Native | Via `__future__` |

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
nested structs, etc. Validation happens automatically when decoding JSON
request bodies.

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
to disable caching. Dependencies can be nested — each `Depends()` callable
can itself declare `Depends()` parameters.

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

Each descriptor maps to a specific part of the HTTP request:

| Descriptor | Source | Example |
|---|---|---|
| `Path()` | URL path segments | `/items/{item_id}` |
| `Query()` | Query string | `?q=search&limit=10` |
| `Header()` | HTTP headers | `X-Token: abc123` |
| `Cookie()` | Cookies | `session=xyz` |
| `Body()` | Request body (JSON) | `{"key": "value"}` |
| `File()` | Multipart file upload | `<input type="file">` |
| `Form()` | Form field | `<input type="text">` |

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

Simply type-annotate a parameter as `BackgroundTasks` and FasterAPI injects
it automatically. Tasks run sequentially after the response is sent, so
they don't block the client.

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

WebSocket connections support text, binary, and JSON messages via
`send_text()` / `receive_text()`, `send_bytes()` / `receive_bytes()`,
and `send_json()` / `receive_json()`.

### Sub-Interpreters (Python 3.13+)

For CPU-bound work, FasterAPI provides sub-interpreter support. Each
sub-interpreter runs with its own GIL, enabling true parallelism without
process overhead — the closest Python equivalent to Go's goroutines:

```python
from FasterAPI import Faster, run_in_subinterpreter

app = Faster()

def heavy_computation(n: int) -> int:
    return sum(i * i for i in range(n))

@app.get("/compute/{n}")
async def compute(n: int):
    # Python 3.13+: sub-interpreter with own GIL (no pickling needed)
    # Python 3.11-3.12: ProcessPoolExecutor fallback (pickle-based)
    result = await run_in_subinterpreter(heavy_computation, n)
    return {"result": result}
```

You can also manage a pool directly:

```python
from FasterAPI import SubInterpreterPool

pool = SubInterpreterPool(max_workers=8)
result = await pool.run(my_func, arg1, arg2)
pool.shutdown()
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

Available middleware:

| Middleware | Purpose |
|---|---|
| `CORSMiddleware` | Cross-Origin Resource Sharing headers |
| `GZipMiddleware` | Compress responses above a size threshold |
| `TrustedHostMiddleware` | Reject requests from untrusted hosts |
| `HTTPSRedirectMiddleware` | Redirect HTTP to HTTPS |
| `BaseHTTPMiddleware` | Base class for writing custom middleware |

### Router

Group routes under a common prefix and set of tags:

```python
from FasterAPI import Faster, FasterRouter

router = FasterRouter(prefix="/api/v1", tags=["v1"])

@router.get("/items")
async def list_items():
    return []

@router.post("/items", status_code=201)
async def create_item():
    return {"id": 1}

app = Faster()
app.include_router(router)
# Routes registered as GET /api/v1/items, POST /api/v1/items
```

---

## Full Example

See `examples/full_crud_app.py` for a complete CRUD API with routing,
validation, dependency injection, background tasks, middleware, WebSocket,
and error handling:

```python
import msgspec
from FasterAPI import (
    BackgroundTasks, CORSMiddleware, Depends, Faster, FasterRouter,
    HTTPException, Path, Query, WebSocket, WebSocketDisconnect, status,
)

app = Faster(title="My API", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])

class User(msgspec.Struct):
    name: str
    email: str

db: dict[str, dict] = {}

async def get_db():
    return db

router = FasterRouter(prefix="/users", tags=["users"])

@router.get("", summary="List users")
async def list_users(store: dict = Depends(get_db)):
    return list(store.values())

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

app.include_router(router)

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

100 routes (50 static + 30 single-param + 20 multi-param), 1,000,000 lookups:

| Router | Time (s) | Ops/s | Speedup |
|---|---|---|---|
| **Radix tree (FasterAPI)** | **1.40** | **~714,000** | **5.9x** |
| Regex (traditional) | 8.32 | ~120,000 | 1.0x |

The radix tree performs O(k) lookups (k = path segment count) regardless
of route count. Regex routers scan every registered pattern linearly —
the more routes you have, the wider the gap.

### HTTP End-to-End Benchmark

Measured with `httpx.AsyncClient`, 10,000 requests at 100 concurrency.
Both frameworks under `uvicorn` on the same machine (Python 3.11):

| Endpoint | FasterAPI (req/s) | FastAPI (req/s) | Speedup |
|---|---|---|---|
| `GET /health` | **391** | 376 | **1.04x** |
| `GET /users/{id}` | 393 | 403 | 0.98x |
| `POST /users` (JSON body) | **408** | 367 | **1.11x** |

**Where FasterAPI shines most:**

- **JSON serialisation**: POST endpoint shows 1.11x speedup from msgspec's
  C-based JSON encoder vs Pydantic + stdlib json
- **Routing-heavy apps**: With 100+ routes, radix tree lookup is 6x faster
  than regex scanning — this compounds on every single request
- **Validation-heavy endpoints**: msgspec Struct validation compiles to C
  code; Pydantic v2 still has a Python validation layer
- **CPU-bound handlers**: Python 3.13 sub-interpreters enable true
  parallelism without process overhead

### Running Benchmarks

```bash
# HTTP head-to-head (requires: pip install fastapi pydantic)
python benchmarks/compare.py
python benchmarks/compare.py --requests 5000 --concurrency 50

# Routing profiler (no extra deps)
python benchmarks/profile_routing.py
python benchmarks/profile_routing.py --lookups 500000
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

- `@app.get()`, `@app.post()`, `@app.put()`, `@app.delete()`, `@app.patch()`
- `Depends()`, `use_cache`, nested dependencies
- `Path()`, `Query()`, `Header()`, `Cookie()`, `Body()`, `File()`, `Form()`
- `app.add_middleware(CORSMiddleware, ...)`, same kwargs
- `HTTPException`, `RequestValidationError`, `app.add_exception_handler()`
- `BackgroundTasks` injection, `bg.add_task()`
- `@app.websocket()`, `await ws.accept()`, send/receive
- `@app.on_startup`, `@app.on_shutdown`
- Auto-generated OpenAPI at `/openapi.json`, Swagger at `/docs`, ReDoc at `/redoc`
- `JSONResponse`, `HTMLResponse`, `PlainTextResponse`, `RedirectResponse`, `StreamingResponse`, `FileResponse`
- `app.include_router(router, prefix=..., tags=...)`

### Step-by-step migration

1. `pip install faster-api`
2. Replace imports: `FastAPI` -> `Faster`, `APIRouter` -> `FasterRouter`
3. Replace models: `class Foo(BaseModel):` -> `class Foo(msgspec.Struct):`, add `import msgspec`
4. Update return values: Pydantic `.dict()` / `.model_dump()` -> `msgspec.to_builtins(obj)` or return fields directly
5. Run your test suite — it should pass with minimal changes

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
dependencies (no Starlette). The request lifecycle:

```
Client Request
    |
    v
ASGI Interface (__call__)
    |
    v
Middleware Chain (CORS, GZip, etc.)
    |
    v
Router (radix tree) ──> 404 if no match
    |
    v
DI Resolver
    ├── Resolve Depends() chains (cached per-request)
    ├── Extract Path / Query / Header / Cookie params
    ├── Decode Body (msgspec.Struct) or Form / File
    └── Inject BackgroundTasks
    |
    v
Route Handler (async or sync)
    |
    v
Response Serialisation (msgspec.json.encode)
    |
    v
Send ASGI Response
    |
    v
Run Background Tasks (if any)
```

Key design decisions:

- **No Starlette dependency** — ASGI protocol handled directly for minimal overhead
- **Radix tree routing** — O(k) lookup, not O(n) regex scan
- **msgspec for everything** — validation, serialisation, JSON encoding all go through the same C extension
- **Python 3.13 sub-interpreters** — true parallelism for CPU-bound work without pickling overhead

---

## Project Structure

```
FasterAPI/                          # Root project directory
|
├── FasterAPI/                      # Python package
│   ├── __init__.py                 # Public API — all exports
│   ├── app.py                      # Faster ASGI application class
│   ├── router.py                   # RadixRouter + FasterRouter
│   ├── request.py                  # Request object (headers, body, form)
│   ├── response.py                 # Response, JSONResponse, HTMLResponse, etc.
│   ├── params.py                   # Path, Query, Body, Header, Cookie, File, Form
│   ├── dependencies.py             # Depends() + DI resolver
│   ├── exceptions.py               # HTTPException, RequestValidationError
│   ├── middleware.py                # CORS, GZip, TrustedHost, HTTPS, Base
│   ├── background.py               # BackgroundTask, BackgroundTasks
│   ├── websocket.py                # WebSocket, WebSocketDisconnect, WebSocketState
│   ├── datastructures.py           # UploadFile, FormData
│   ├── concurrency.py              # Sub-interpreters (3.13+), thread/process pools
│   ├── testclient.py               # TestClient (httpx-based, sync)
│   ├── status.py                   # HTTP status code constants
│   └── openapi/
│       ├── __init__.py
│       ├── generator.py            # OpenAPI 3.0.3 spec generation
│       └── ui.py                   # Swagger UI + ReDoc HTML templates
│
├── tests/
│   ├── __init__.py
│   ├── test_routing.py             # Radix router: static, param, method matching
│   ├── test_params.py              # Request parsing + parameter descriptors
│   ├── test_deps.py                # Dependency injection + caching
│   ├── test_responses.py           # All response classes + ASGI output
│   ├── test_exceptions.py          # HTTP exceptions + custom handlers
│   ├── test_openapi.py             # OpenAPI spec generation + UI routes
│   ├── test_middleware.py          # CORS, GZip, TrustedHost, HTTPS
│   ├── test_websocket.py           # WebSocket lifecycle + app integration
│   ├── test_background.py          # Background task execution
│   ├── test_formdata.py            # File uploads, form parsing, DI injection
│   ├── test_integration.py         # Full CRUD + edge cases
│   └── test_benchmark.py           # Performance regression guards
│
├── examples/
│   ├── basic_app.py                # Minimal hello world
│   ├── full_crud_app.py            # Complete CRUD with all features
│   └── websocket_app.py            # WebSocket echo + chat room
│
├── benchmarks/
│   ├── compare.py                  # FasterAPI vs FastAPI HTTP head-to-head
│   ├── profile_routing.py          # Radix tree vs regex cProfile
│   └── README.md                   # Benchmark methodology
│
├── .github/
│   └── workflows/
│       ├── ci.yml                  # Test on Python 3.11, 3.12, 3.13
│       └── release.yml             # Build + publish to PyPI on tags
│
├── pyproject.toml                  # Build config, deps, tool settings
├── CHANGELOG.md                    # Release history
└── README.md                       # This file
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
