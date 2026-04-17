# FasterAPI

[![PyPI version](https://img.shields.io/pypi/v/faster-api-web.svg?logo=pypi&logoColor=white)](https://pypi.org/project/faster-api-web/)
[![GitHub release](https://img.shields.io/github/v/release/FasterApiWeb/FasterAPI?include_prereleases&sort=semver&logo=github&label=release)](https://github.com/FasterApiWeb/FasterAPI/releases)
[![PyPI - Python](https://img.shields.io/pypi/pyversions/faster-api-web.svg)](https://pypi.org/project/faster-api-web/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/faster-api-web.svg)](https://pypi.org/project/faster-api-web/)
[![CI](https://github.com/FasterApiWeb/FasterAPI/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/FasterApiWeb/FasterAPI/actions/workflows/ci.yml?query=branch%3Amaster)
[![Benchmark](https://github.com/FasterApiWeb/FasterAPI/actions/workflows/benchmark.yml/badge.svg?branch=master)](https://github.com/FasterApiWeb/FasterAPI/actions/workflows/benchmark.yml?query=branch%3Amaster)
[![Docs workflow](https://github.com/FasterApiWeb/FasterAPI/actions/workflows/docs.yml/badge.svg?branch=master)](https://github.com/FasterApiWeb/FasterAPI/actions/workflows/docs.yml?query=branch%3Amaster)
[![Docs site live](https://img.shields.io/website?url=https%3A%2F%2Ffasterapiweb.github.io%2FFasterAPI%2F&up_message=online&down_message=offline&label=docs%20site)](https://fasterapiweb.github.io/FasterAPI/)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-5c6bc0?logo=githubpages)](https://fasterapiweb.github.io/FasterAPI/)
[![codecov](https://codecov.io/gh/FasterApiWeb/FasterAPI/branch/master/graph/badge.svg)](https://codecov.io/gh/FasterApiWeb/FasterAPI)
[![License: MIT](https://img.shields.io/github/license/FasterApiWeb/FasterAPI)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue?logo=docker)](https://ghcr.io/fasterapiweb/fasterapi)
[![TestPyPI](https://img.shields.io/badge/TestPyPI-faster--api--web-informational)](https://test.pypi.org/project/faster-api-web/)
[![Hatch build](https://img.shields.io/badge/packaging-hatch-3775A9?logo=python)](https://github.com/pypa/hatch)
[![GitHub contributors](https://img.shields.io/github/contributors/FasterApiWeb/FasterAPI)](https://github.com/FasterApiWeb/FasterAPI/graphs/contributors)
[![GitHub last commit](https://img.shields.io/github/last-commit/FasterApiWeb/FasterAPI/master)](https://github.com/FasterApiWeb/FasterAPI/commits/master)
[![uvloop](https://img.shields.io/badge/uvloop-supported-2ea44f)](https://github.com/MagicStack/uvloop)
[![msgspec](https://img.shields.io/badge/msgspec-models-blue)](https://jcristharif.com/msgspec/)
[![ASGI](https://img.shields.io/badge/ASGI-3.0-lightgrey)](https://asgi.readthedocs.io/en/latest/)
[![GitHub stars](https://img.shields.io/github/stars/FasterApiWeb/FasterAPI?style=social)](https://github.com/FasterApiWeb/FasterAPI)

---

**Documentation:** [fasterapiweb.github.io/FasterAPI](https://fasterapiweb.github.io/FasterAPI/) (Python **3.13** first; see [Python 3.13 & compatibility](https://fasterapiweb.github.io/FasterAPI/python-313/))  
**Source code:** [github.com/FasterApiWeb/FasterAPI](https://github.com/FasterApiWeb/FasterAPI)  
**PyPI package:** [`faster-api-web`](https://pypi.org/project/faster-api-web/) — `pip install faster-api-web`

---

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

## Acknowledgments

**FastAPI** ([github.com/fastapi/fastapi](https://github.com/fastapi/fastapi)) showed what a modern Python API framework can be. **Sebastián Ramírez** ([@tiangolo](https://github.com/tiangolo)), creator of FastAPI, inspired this project. FasterAPI is independent software with different internals; it is not affiliated with the FastAPI team.

Full credit and links: [Acknowledgments](https://fasterapiweb.github.io/FasterAPI/acknowledgments/) in the docs.

---

## Cite this repository

**Author:** Eshwar Chandra Vidhyasagar Thedla · **GitHub:** [@EshwarCVS](https://github.com/EshwarCVS) · **Repository:** [FasterApiWeb/FasterAPI](https://github.com/FasterApiWeb/FasterAPI)

GitHub shows a **Cite this repository** button when [`CITATION.cff`](CITATION.cff) is on the default branch. You can also use:

```bibtex
@software{faster_api_web,
  author = {Thedla, Eshwar Chandra Vidhyasagar},
  title = {faster-api-web (FasterAPI): high-performance ASGI web framework for Python},
  url = {https://github.com/FasterApiWeb/FasterAPI},
  year = {2026},
}
```

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
  routes are registered. With 100 routes, this delivers **~7.6x faster
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
| **Routing** | Radix tree (O(k) lookup, ~7.6x faster) | Regex-based (Starlette) |
| **Event loop** | uvloop (auto) / stdlib on 3.13+ | stdlib asyncio |
| **JSON encoding** | msgspec.json (C extension) | stdlib json / orjson opt-in |
| **CPU parallelism** | Sub-interpreters (3.13+) / ProcessPool (3.11+) | N/A |
| **Dependency injection** | Built-in, same `Depends()` API | Built-in `Depends()` |
| **OpenAPI docs** | Auto-generated, Swagger + ReDoc | Auto-generated, Swagger + ReDoc |
| **WebSocket** | Built-in | Built-in (via Starlette) |
| **Middleware** | CORS, GZip, TrustedHost, HTTPS | CORS, GZip, TrustedHost, HTTPS |
| **Background tasks** | Built-in `BackgroundTasks` | Built-in `BackgroundTasks` |
| **Test client** | Built-in `TestClient` (httpx) | Via Starlette `TestClient` |
| **Python version** | 3.13 first, 3.10+ supported | 3.8+ |

---

## Installation

```bash
pip install faster-api-web
```

For maximum performance (includes uvloop):

```bash
pip install faster-api-web[all]
```

Or install from source:

```bash
git clone https://github.com/FasterApiWeb/FasterAPI.git
cd FasterAPI
pip install -e ".[dev]"
```

### Requirements

**FasterAPI stands on the shoulders of these libraries** (see also [FastAPI’s “Requirements” idea](https://github.com/fastapi/fastapi#requirements)):

- **[msgspec](https://jcristharif.com/msgspec/)** — structs, validation, and JSON encoding.
- **[uvicorn](https://www.uvicorn.org/)** `[standard]` — ASGI server (pulled in by this package).
- **[python-multipart](https://github.com/Kludex/python-multipart)** — forms and uploads.
- Optional: **[uvloop](https://github.com/MagicStack/uvloop)** via `faster-api-web[all]` for lower event-loop overhead on Linux.

**Python:**

- **Python 3.13** (recommended) — full sub-interpreter support, faster asyncio
- **Python 3.12** — partial per-interpreter GIL support, ProcessPool fallback
- **Python 3.10** — minimum supported version, ProcessPool fallback

### Python Version Compatibility

| Feature | 3.13+ | 3.12 | 3.10–3.11 |
|---|---|---|---|
| Sub-interpreters (own GIL) | Native | ProcessPool fallback | ProcessPool fallback |
| asyncio performance | Excellent (PEP 703 prep) | Good | Good |
| uvloop benefit | Optional (~10-15% faster) | Recommended (~2-3x faster) | Recommended (~2-3x faster) |
| Type syntax (`X \| Y`) | Native | Native | Via `__future__` on 3.10 |

---

## Documentation

Tutorials and reference are published from the `docs/` folder with **MkDocs** — same topics as in this README, with **Python 3.13** as the primary target and a dedicated **[compatibility](https://fasterapiweb.github.io/FasterAPI/python-313/)** page for 3.10–3.12.

The live site is deployed by the **[Docs workflow](.github/workflows/docs.yml)** to **GitHub Pages**. In the repository **Settings → Pages → Build and deployment**, the **source must be “GitHub Actions”** (not the legacy `gh-pages` branch); otherwise the published URL can 404 even when the workflow succeeds.

---

## Releases and PyPI versions

The **PyPI** package name is **`faster-api-web`**. Published versions are tied to **git tags** on
`master` (`v0.1.2`, …): pushing a tag runs the [Release workflow](.github/workflows/release.yml),
which builds the wheel/sdist (version comes from the tag via **hatch-vcs**), publishes to **PyPI**,
and creates a GitHub Release. **You do not bump a hardcoded version in `pyproject.toml` for releases**
— tag the commit you want to ship.

For branch-channel previews, merges to `dev`, `stage`, and `master` publish to **TestPyPI** with valid
PEP 440 channel versions:
- `dev` branch: `0.0.0.devN`
- `stage` branch: `0.0.0aN`
- `master` branch preview: `0.0.0rcN`

Release intent is controlled by PR labels (`release:patch`, `release:minor`, `release:major`) which
drive automatic tag creation on merge.

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
    HTTPException, Path, Query, WebSocket, WebSocketDisconnect,
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

@router.post("", summary="Create user", status_code=201)
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

> Python 3.13.7, macOS, Apple Silicon (M-series).
> Reproduce with `python benchmarks/compare.py --direct`.

<!-- AUTO_BENCHMARKS_START -->

### Auto-updated branch benchmark snapshot (CI)

| Endpoint | FasterAPI | FastAPI | Speedup |
|---|---|---|---|
| `GET /health` | **481 req/s** | 477 req/s | **1.01x** |
| `GET /users/{id}` | **515 req/s** | 516 req/s | **1.00x** |
| `POST /users` | **450 req/s** | 454 req/s | **0.99x** |

| Routing | Radix ops/s | Regex ops/s | Speedup |
|---|---|---|---|
| 100-route lookup | **976,864** | 95,599 | **10.2x** |

_This block is updated automatically on pushes to `dev`, `stage`, and `master`._

<!-- AUTO_BENCHMARKS_END -->

### Framework-Level Benchmark (Direct ASGI)

This is the most meaningful benchmark — it calls each framework's ASGI
`__call__` directly, eliminating TCP, HTTP parsing, and httpx overhead.
It measures pure framework speed: routing, dependency injection,
serialization, and response construction.

100,000 requests per endpoint, single-threaded:

| Endpoint | FasterAPI | FastAPI | Speedup |
|---|---|---|---|
| `GET /health` | **335,612 req/s** | 49,005 req/s | **6.85x** |
| `GET /users/{id}` | **282,835 req/s** | 32,391 req/s | **8.73x** |
| `POST /users` (JSON body) | **193,225 req/s** | 27,031 req/s | **7.15x** |

### Component-Level Benchmarks

These isolate each innovation independently:

**Routing — 100 routes, 3M lookups**

| Router | Ops/s | Speedup |
|---|---|---|
| **Radix tree (FasterAPI)** | **1,104,318** | **7.6x** |
| Regex (traditional) | 144,822 | 1.0x |

**JSON Encoding — dict → bytes, 500K iterations**

| Encoder | Ops/s | Speedup |
|---|---|---|
| **msgspec.json.encode** | **6,317,891** | **9.4x** |
| json.dumps + .encode() | 670,234 | 1.0x |

**JSON Decode + Validate — bytes → typed object, 500K iterations**

| Decoder | Ops/s | Speedup |
|---|---|---|
| **msgspec.json.decode (typed)** | **3,348,927** | **3.7x** |
| Pydantic v2 validate_json | 909,256 | 1.0x |
| json.loads (untyped) | 708,006 | 0.8x |

### Why FasterAPI Is Faster

The speedup comes from eliminating Python overhead in the hot path:

1. **No per-request introspection** — Handler signatures are compiled once at
   startup. FastAPI calls `inspect.signature()` and `get_type_hints()` on
   every request.
2. **Radix tree routing** — O(k) lookup (k = path segments). FastAPI uses
   Starlette's regex router which scans all patterns linearly.
3. **msgspec zero-copy** — JSON bytes decode directly to typed structs in C.
   No intermediate `dict`, no Python validation loop.
4. **Minimal ASGI overhead** — No Starlette dependency. Request/response
   objects use `__slots__` and lazy property parsing.

### Running Benchmarks

```bash
# Direct ASGI benchmark (recommended, most accurate)
python benchmarks/compare.py --direct

# Full HTTP comparison through uvicorn (requires: pip install fastapi pydantic)
python benchmarks/compare.py
python benchmarks/compare.py --requests 20000 --concurrency 200
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

1. `pip install faster-api-web`
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
FasterAPI/
├── FasterAPI/
│   ├── __init__.py
│   ├── app.py               # Core Faster class
│   ├── router.py            # RadixRouter + FasterRouter
│   ├── request.py           # Request object
│   ├── response.py          # Response, JSONResponse, etc
│   ├── params.py            # Path, Query, Body, Header, Cookie
│   ├── dependencies.py      # Depends() system
│   ├── middleware.py        # CORS, GZip, Trusted Hosts
│   ├── exceptions.py        # HTTPException, handlers
│   ├── background.py        # BackgroundTasks
│   ├── websocket.py         # WebSocket support
│   ├── datastructures.py    # UploadFile, Form
│   ├── openapi/
│   │   ├── __init__.py
│   │   ├── generator.py     # Auto OpenAPI schema gen
│   │   └── ui.py            # Swagger + ReDoc HTML
│   ├── testclient.py        # TestClient (httpx)
│   └── concurrency.py       # CPU/IO detection, executors
├── tests/
│   ├── test_routing.py
│   ├── test_params.py
│   ├── test_deps.py
│   ├── test_openapi.py
│   ├── test_middleware.py
│   ├── test_websocket.py
│   └── test_benchmark.py
├── examples/
│   ├── basic_app.py
│   ├── full_crud_app.py
│   └── websocket_app.py
├── benchmarks/
│   └── compare.py           # FasterAPI vs FastAPI vs Fiber
├── pyproject.toml
├── README.md
└── .github/
    └── workflows/
        └── ci.yml
```

---

## Performance Innovations

FasterAPI achieves its speed through five key architectural decisions:

| Innovation | What It Does | Speedup Source |
|---|---|---|
| **uvloop** | Replaces stdlib asyncio with libuv-backed C event loop | 2-4x faster I/O scheduling |
| **msgspec** | C extension JSON encode/decode + validation in one pass | 10-20x faster than Pydantic v1 |
| **Radix tree router** | O(k) path lookup (k = segments) instead of O(n) regex scan | 7.6x faster with 100+ routes |
| **Compiled DI** | Handler signatures introspected once at startup, not per-request | Eliminates ~80% of per-request overhead |
| **Zero-copy responses** | `msgspec.json.encode()` → bytes directly, no intermediate str | 50% fewer memory allocations |

### How They Work Together

```
Incoming Request
      │
      ▼
  Radix Tree Router          ← O(k) lookup, no regex
      │
      ▼
  Pre-compiled DI Resolver   ← No inspect.signature() per request
      │
      ▼
  msgspec.json.decode()      ← C extension, one-pass validate + parse
      │
      ▼
  Handler (uvloop-scheduled)  ← C event loop, minimal overhead
      │
      ▼
  msgspec.json.encode()      ← C extension, zero-copy to bytes
      │
      ▼
  Raw bytes → Client
```

---

## Contributing

We use a **three-tier branch model** to keep `master` stable:

```
dev/your-feature ──PR──▶ stage ──PR──▶ master ──tag──▶ release
```

| Branch | Purpose | Direct push |
|---|---|---|
| `master` | Production releases | **Nobody** — PR from `stage` only |
| `stage` | Integration & QA | Maintainer only |
| `dev/*` | Your feature/fix | You |

### Flow in Practice

**As a contributor:**
```bash
git checkout stage && git pull origin stage
git checkout -b dev/my-feature
# ... make changes ...
git push -u origin dev/my-feature
# Open PR → stage
```

CI automatically runs **tests on Python 3.10–3.13** (coverage must stay **≥ 85%**) and **benchmarks**
on every PR. The benchmark workflow enforces **ASGI and routing floors** from `benchmarks/baseline.json`
and posts a table comparing **FasterAPI, FastAPI, and Fiber (Go)**.

After approval → merge to `stage`.

### Local checks

```bash
git clone https://github.com/FasterApiWeb/FasterAPI.git && cd FasterAPI
pip install -e ".[dev]"
pytest --cov=FasterAPI --cov-report=term-missing --cov-fail-under=85
mypy FasterAPI/
pip install -e ".[benchmark]" && python benchmarks/compare.py --direct
```

For docs: `pip install -e ".[docs]" && mkdocs serve`. Security reports: see [SECURITY.md](SECURITY.md).

**As the maintainer (release cycle):**
```bash
# Open PR: stage → master
# CI + benchmarks run again
# Merge → tag on master:
git checkout master && git pull
git tag v0.x.0 && git push origin v0.x.0
# Release workflow auto-publishes to PyPI + Docker + GitHub Releases
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full details.

---

## Roadmap

### v0.2.0 — Production Hardening
- [ ] Streaming request body support (large file uploads without full buffering)
- [ ] HTTP/2 support via hypercorn/daphne compatibility
- [ ] Connection pooling for database middleware
- [ ] Rate limiting middleware
- [ ] Request ID / correlation ID middleware
- [ ] Structured logging integration (structlog)

### v0.3.0 — Ecosystem
- [ ] SQLAlchemy async session dependency
- [ ] Redis cache middleware
- [ ] JWT authentication middleware
- [ ] OAuth2 password/bearer flow
- [ ] CLI tool (`fasterapi run`, `fasterapi new`)

### v0.4.0 — Performance
- [ ] Cython-compiled hot paths (router, DI resolver)
- [ ] HTTP/3 (QUIC) support
- [ ] Connection-level keep-alive optimisation
- [ ] Pre-serialised response caching

### v1.0.0 — Stable Release
- [ ] Full test coverage (>95%)
- [ ] Production deployment guides (Docker, K8s, systemd)
- [ ] Migration tool (`fasterapi migrate-from-fastapi`)
- [x] Performance regression CI (automated benchmarks on every PR)

---

## License

[MIT](LICENSE) -- Eshwar Chandra Vidhyasagar Thedla
