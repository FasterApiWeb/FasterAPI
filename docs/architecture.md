# Architecture

This page explains FasterAPI's internal architecture. Read this before contributing — it covers why each component exists and how they interact.

---

## Request Lifecycle

```
Incoming ASGI Request
       │
       ▼
┌──────────────────────────┐
│  Middleware Chain         │  Built once at first request, cached.
│  (CORS → GZip → ...)    │  Each middleware wraps the next as an ASGI app.
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│  Faster.__call__         │  ASGI entry point. Routes to HTTP, WebSocket,
│                          │  or Lifespan handler based on scope["type"].
└────────────┬─────────────┘
             │ (HTTP)
             ▼
┌──────────────────────────┐
│  RadixRouter.resolve()   │  O(k) path lookup (k = path segments).
│                          │  Returns (handler, path_params, metadata).
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│  _resolve_handler()      │  Iterates pre-compiled _ParamSpec tuples.
│                          │  Injects dependencies, parses params.
│                          │  Zero per-request introspection.
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│  Handler executes        │  async def → event loop (uvloop)
│                          │  plain def → process pool (CPU auto-detect)
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│  _send_response()        │  dict/Struct → msgspec.json.encode → bytes
│                          │  Zero-copy: Rust encodes directly to bytes.
│                          │  Pre-encoded headers avoid repeated .encode().
└────────────┬─────────────┘
             │
             ▼
        Response sent
             │
             ▼ (if any)
       BackgroundTasks.run()
```

---

## 1. Radix Tree Router

**File:** `FasterAPI/router.py`

### Why not regex?

FastAPI (via Starlette) compiles each route path into a regex pattern and checks them sequentially on every request — O(n) where n = total routes. This is fine for 10 routes, but at 100+ routes the linear scan becomes measurable overhead.

### How the radix tree works

Routes are decomposed into segments and inserted into a tree at startup:

```
Registered routes:
  GET /users
  GET /users/{id}
  GET /users/{id}/posts
  GET /health
  GET /orgs/{org_id}/teams/{team_id}

Tree structure:

         root
        /    \
    users    health → handler
      |        
    [leaf] → handler (GET /users)
      |
     {id} → handler (GET /users/{id})
      |
    posts → handler (GET /users/{id}/posts)

    orgs
      |
    {org_id}
      |
    teams
      |
    {team_id} → handler
```

### Resolution algorithm

The `_walk` method uses **iterative traversal** (not recursion) for the common case:

```python
while idx < n:
    seg = segments[idx]
    child = node.children.get(seg)      # Try static match first
    if child is not None:
        node = child; idx += 1; continue
    param_child = node.children.get("*") # Then try param wildcard
    if param_child is not None:
        params[param_child.param_name] = seg
        node = param_child; idx += 1; continue
    return None                          # No match
```

**Key design choices:**

- Static children are checked before param wildcards (most routes are static segments)
- `__slots__` on `RadixNode` eliminates per-instance `__dict__` — less memory, faster attribute access
- Path splitting uses a list comprehension (`[s for s in path.split("/") if s]`) — this hits CPython's fast C path

### Complexity

| Operation | Radix Tree | Regex (Starlette) |
|---|---|---|
| Lookup | O(k) where k = path segments | O(n) where n = total routes |
| 100 routes | ~3 segment checks | ~50 regex evaluations (avg) |

---

## 2. Compiled Dependency Injection

**File:** `FasterAPI/dependencies.py`

### The problem

FastAPI calls `inspect.signature()` and `typing.get_type_hints()` on **every request** to figure out what a handler needs. These are expensive reflection operations.

### The solution: compile once, resolve many

At route registration time, `compile_handler(func)` introspects the handler once and produces a tuple of `_ParamSpec` objects:

```
Route registration (startup):
  @app.get("/users/{id}")
  async def get_user(id: str = Path(), q: str = Query(None)):
      ...

  compile_handler(get_user) is called immediately.
  Returns: (
      _ParamSpec(name="id",  kind=_KIND_PATH,  ...),
      _ParamSpec(name="q",   kind=_KIND_QUERY, ...),
  ), is_async=True
```

At request time, `_resolve_from_specs` iterates the pre-compiled tuple with integer kind comparisons — no reflection, no isinstance chains:

```
Request time (hot path):
  for spec in specs:
      if spec.kind == _KIND_PATH:   kwargs[spec.name] = path_params[spec.name]
      elif spec.kind == _KIND_QUERY: kwargs[spec.name] = request.query_params.get(...)
      ...
```

### _ParamSpec design

```python
class _ParamSpec:
    __slots__ = ("name", "kind", "annotation", "default", "marker")
```

- `kind` is an integer constant (0–11), not an enum — integer comparison is faster than `isinstance`
- `__slots__` avoids `__dict__` overhead
- `@lru_cache(maxsize=512)` on `compile_handler` means the same function is never introspected twice
- Dependencies (`Depends(...)`) are compiled recursively — the entire dependency tree is pre-resolved

---

## 3. Request Object — Lazy Parsing

**File:** `FasterAPI/request.py`

Most handlers only need 1-2 request attributes (e.g., path params and body). Parsing all headers, query params, and cookies on every request wastes time.

FasterAPI's `Request` uses lazy properties:

```python
@property
def headers(self) -> dict[str, str]:
    h = self._headers           # Check cache
    if h is None:               # First access → parse
        raw = self._scope.get("headers", [])
        h = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in raw}
        self._headers = h       # Cache for subsequent access
    return h
```

The same pattern applies to `query_params`, `cookies`, and `body`. If a handler never accesses `request.cookies`, they're never parsed.

---

## 4. Middleware Chain

**File:** `FasterAPI/middleware.py`

### How the chain is built

Middleware is registered via `app.add_middleware(CORSMiddleware, allow_origins=["*"])` and stored as `(class, kwargs)` pairs.

On the first request, the chain is built **once** by wrapping the core app in reverse order:

```
Registration order:     [CORS, GZip, TrustedHost]
Build order (reversed): TrustedHost(GZip(CORS(app)))

Request flow:
  → TrustedHost.__call__  (checks Host header)
    → GZip.__call__       (buffers response for compression)
      → CORS.__call__     (injects CORS headers)
        → app._asgi_app   (route dispatch)
```

The built chain is cached in `self._middleware_app`. Adding middleware after the first request invalidates the cache (sets it to `None`).

### ASGI middleware pattern

Each middleware is a valid ASGI app that wraps another ASGI app:

```python
class CORSMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, **kwargs):
        self.app = app  # The next app in the chain

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)  # Pass through non-HTTP
            return
        await self.dispatch(scope, receive, send)
```

---

## 5. Response Path — Zero-Copy JSON

**File:** `FasterAPI/app.py` (module-level `_send_response`)

When a handler returns a dict or msgspec Struct, the response path is:

```
dict → msgspec.json.encode(dict) → bytes → ASGI send

One allocation. msgspec's Rust core converts Python objects directly
to JSON bytes without an intermediate string step.
```

Compare to the standard approach:

```
dict → json.dumps(dict) → str → str.encode("utf-8") → bytes → send

Three allocations. Each creates a new Python object the GC must track.
```

Additionally, common header values are pre-encoded as module-level bytes constants:

```python
_CT_JSON = b"application/json"
_HEADER_CT = b"content-type"
```

This avoids calling `.encode()` on every response.

---

## 6. Event Loop — uvloop

**File:** `FasterAPI/concurrency.py`

uvloop replaces Python's default asyncio event loop with one backed by libuv (the same C library that powers Node.js). It handles I/O polling, callback scheduling, and timer management in C instead of Python.

```python
def install_event_loop() -> str:
    try:
        import uvloop
        if _PY312_PLUS:
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        else:
            uvloop.install()
        return "uvloop"
    except ImportError:
        return "asyncio"
```

This is called at module import time (`_event_loop = install_event_loop()`) so it's set before any async code runs.

---

## File Map

| File | Responsibility |
|---|---|
| `app.py` | ASGI entry point, route registration, HTTP/WS/lifespan dispatch |
| `router.py` | Radix tree router + FasterRouter (sub-router/blueprint) |
| `dependencies.py` | Compiled DI, `Depends()`, param resolution |
| `request.py` | Lazy-parsed Request object |
| `response.py` | Response classes (JSON, HTML, Streaming, File) |
| `middleware.py` | CORS, GZip, TrustedHost, HTTPS redirect |
| `concurrency.py` | uvloop, sub-interpreters, thread/process pools |
| `exceptions.py` | HTTPException, validation errors, default handlers |
| `params.py` | Path, Query, Body, Header, Cookie, File, Form descriptors |
| `background.py` | BackgroundTasks (post-response execution) |
| `websocket.py` | WebSocket connection handler |
| `datastructures.py` | UploadFile, FormData |
| `openapi/` | Auto-generated OpenAPI 3.0 schema + Swagger/ReDoc UI |
