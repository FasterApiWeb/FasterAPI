# API Reference

This page documents every public class and function exported from `FasterAPI`.
For the full list of re-exports, see
[`FasterAPI/__init__.py`](https://github.com/FasterApiWeb/FasterAPI/blob/master/FasterAPI/__init__.py).

## Application

### `Faster`

The main ASGI application class.

```python
from FasterAPI import Faster

app = Faster(
    title="My API",           # shown in Swagger UI
    version="1.0.0",          # shown in Swagger UI
    description="...",        # Markdown description
    openapi_url="/openapi.json",  # set to None to disable
    docs_url="/docs",         # Swagger UI; None to disable
    redoc_url="/redoc",       # ReDoc; None to disable
)
```

**Route decorators:** `@app.get`, `@app.post`, `@app.put`, `@app.delete`,
`@app.patch`, `@app.websocket`

**Lifecycle:** `@app.on_startup`, `@app.on_shutdown`

**Middleware:** `app.add_middleware(MiddlewareClass, **kwargs)`

**Exception handlers:** `app.add_exception_handler(ExcClass, handler)`

**Router inclusion:** `app.include_router(router, prefix="", tags=())`

---

### `FasterRouter`

Groups related routes into a reusable router.

```python
from FasterAPI import FasterRouter

router = FasterRouter()

@router.get("/")
async def list_items(): ...

app.include_router(router, prefix="/items", tags=["items"])
```

---

## Request & Response

### `Request`

Represents an incoming HTTP request.

```python
from FasterAPI import Request

@app.get("/info")
async def info(request: Request):
    return {
        "method": request.method,
        "path": request.url.path,
        "client": request.client,
    }
```

**Key attributes:**

| Attribute | Type | Description |
|---|---|---|
| `method` | `str` | HTTP verb |
| `url` | URL | Full URL |
| `headers` | Headers | Request headers (case-insensitive) |
| `query_params` | QueryParams | Parsed query string |
| `cookies` | `dict[str, str]` | Parsed cookies |
| `client` | `tuple[str, int] \| None` | Client IP and port |
| `path_params` | `dict[str, str]` | Matched path segments |

**Async methods:** `await request.body()`, `await request.json()`,
`await request.form()`

---

### `Response`

Base HTTP response. All response classes accept `content`, `status_code`, `headers`,
and optionally `media_type`.

```python
from FasterAPI import Response

return Response(content=b"raw bytes", status_code=200, media_type="text/plain")
```

---

### `JSONResponse`

Serialises content with `msgspec.json.encode`.

```python
from FasterAPI import JSONResponse

return JSONResponse({"key": "value"}, status_code=200)
```

---

### `HTMLResponse`

Sets `Content-Type: text/html`.

```python
from FasterAPI import HTMLResponse

return HTMLResponse("<h1>Hello</h1>")
```

---

### `PlainTextResponse`

Sets `Content-Type: text/plain`.

```python
from FasterAPI import PlainTextResponse

return PlainTextResponse("OK")
```

---

### `RedirectResponse`

Issues an HTTP redirect.

```python
from FasterAPI import RedirectResponse

return RedirectResponse(url="/new-path", status_code=307)
```

---

### `StreamingResponse`

Streams body from an async or sync iterator.

```python
from FasterAPI import StreamingResponse

async def gen():
    yield b"chunk1"
    yield b"chunk2"

return StreamingResponse(gen(), media_type="text/plain")
```

---

### `FileResponse`

Serves a file from disk with `Content-Disposition: attachment`.

```python
from FasterAPI import FileResponse

return FileResponse("report.pdf", filename="report.pdf")
```

---

## Parameters

### `Path`

Marks a parameter as coming from the URL path. Usage: `item_id: int = Path()`.

### `Query`

Marks a parameter as coming from the query string.

```python
from FasterAPI import Query

async def search(q: str | None = Query(default=None, alias="search")): ...
```

### `Header`

Marks a parameter as coming from a request header. Underscores in the parameter name
are converted to hyphens by default (`convert_underscores=True`).

```python
from FasterAPI import Header

async def handler(user_agent: str | None = Header(default=None)): ...
# reads "User-Agent" header
```

### `Cookie`

Marks a parameter as coming from a cookie.

```python
from FasterAPI import Cookie

async def handler(session: str | None = Cookie(default=None)): ...
```

### `Body`

Marks a parameter as coming from the raw JSON request body.

```python
from FasterAPI import Body

async def handler(data: dict = Body()): ...
```

### `Form`

Marks a parameter as coming from form data.

```python
from FasterAPI import Form

async def login(username: str = Form(), password: str = Form()): ...
```

### `File`

Marks a parameter as an uploaded file.

```python
from FasterAPI import File, UploadFile

async def upload(file: UploadFile = File()): ...
```

---

## Dependency Injection

### `Depends`

Declares a dependency to be resolved before the route handler.

```python
from FasterAPI import Depends

async def get_db(): ...

@app.get("/items")
async def handler(db = Depends(get_db)): ...
```

Parameters:
- `dependency` — callable to resolve
- `use_cache=True` — if `True`, calls dependency once per request

---

## Exceptions

### `HTTPException`

```python
from FasterAPI import HTTPException

raise HTTPException(status_code=404, detail="Not found")
raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Bearer"})
```

### `RequestValidationError`

Raised automatically when a path/query/body parameter fails validation.

```python
from FasterAPI.exceptions import RequestValidationError

app.add_exception_handler(RequestValidationError, my_handler)
```

---

## Middleware

### `BaseHTTPMiddleware`

Subclass to write custom middleware:

```python
from FasterAPI import BaseHTTPMiddleware

class MyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, scope, receive, send):
        # before
        await self.app(scope, receive, send)
        # after
```

### `CORSMiddleware`

```python
from FasterAPI import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
    max_age=600,
)
```

### `GZipMiddleware`

```python
from FasterAPI import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)
```

### `TrustedHostMiddleware`

```python
from FasterAPI import TrustedHostMiddleware

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["example.com"])
```

### `HTTPSRedirectMiddleware`

```python
from FasterAPI import HTTPSRedirectMiddleware

app.add_middleware(HTTPSRedirectMiddleware)
```

---

## Background Tasks

### `BackgroundTasks`

```python
from FasterAPI import BackgroundTasks

@app.post("/items")
async def create(tasks: BackgroundTasks):
    tasks.add_task(send_email, "user@example.com")
    return {"queued": True}
```

### `BackgroundTask`

Single task wrapper:

```python
from FasterAPI import BackgroundTask

task = BackgroundTask(send_email, "user@example.com")
```

---

## WebSocket

### `WebSocket`

```python
from FasterAPI import WebSocket

@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    data = await ws.receive_text()
    await ws.send_text(f"Echo: {data}")
```

Methods: `accept()`, `receive_text()`, `receive_bytes()`, `receive_json()`,
`send_text()`, `send_bytes()`, `send_json()`, `close(code=1000)`

### `WebSocketDisconnect`

Exception raised when the client disconnects.

### `WebSocketState`

Enum: `CONNECTING`, `CONNECTED`, `DISCONNECTED`

---

## Data Structures

### `UploadFile`

Represents an uploaded file:

| Attribute / method | Description |
|--------------------|-------------|
| `filename` | Original filename |
| `content_type` | MIME type |
| `await file.read()` | Read all bytes |

### `FormData`

Mapping-like object returned by `await request.form()`.

---

## Concurrency

### `SubInterpreterPool`

CPU-parallel worker pool using Python 3.13 sub-interpreters (falls back to
`ProcessPoolExecutor` on earlier versions).

```python
from FasterAPI import SubInterpreterPool

pool = SubInterpreterPool(max_workers=4)
```

### `run_in_subinterpreter`

Run a function in a sub-interpreter and return an `asyncio.Future`:

```python
from FasterAPI import run_in_subinterpreter

result = await run_in_subinterpreter(heavy_function, arg1, arg2)
```

---

## Auto-generated docs

::: FasterAPI
