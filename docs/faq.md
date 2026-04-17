# FAQ & Troubleshooting

## Installation

### `pip install faster-api-web` succeeds but `import FasterAPI` fails

Make sure you are importing with the correct capitalisation:

```python
from FasterAPI import Faster   # capital F, API
```

The PyPI package name is `faster-api-web`; the Python package directory is `FasterAPI`.

### `ImportError: TestClient requires httpx`

```bash
pip install httpx
# or
pip install faster-api-web[test]
```

### uvloop is not being used

```bash
pip install faster-api-web[all]
```

uvloop is only installed as an optional extra and only activates on Linux.

---

## Running the app

### `uvicorn main:app --reload` — `app` not found

Make sure your file is named `main.py` and it contains `app = Faster()`.

### Port already in use

```bash
uvicorn main:app --port 8001
# or find and kill the process
lsof -ti:8000 | xargs kill -9
```

### Swagger UI (`/docs`) shows no routes

Routes must be registered **before** the first request.  If you use `include_router`,
call it before uvicorn starts, not inside a handler.

---

## Request handling

### 422 Unprocessable Entity on valid-looking input

Check:
1. `Content-Type: application/json` header is set.
2. The JSON matches the struct field types exactly (e.g. `int` vs `str`).
3. Required fields are present and not `null`.

```bash
curl -X POST /items \
  -H "Content-Type: application/json" \
  -d '{"name":"Widget","price":9.99}'
```

### Path parameter is always `None`

Path parameters must appear in the URL pattern:

```python
@app.get("/items/{item_id}")   # {item_id} in the path
async def get_item(item_id: int):
    ...
```

### Query parameter not received

Check the URL encoding.  Spaces should be `%20` or `+`.

```bash
curl "http://localhost:8000/search?q=hello%20world"
```

### File upload returns `422`

Make sure the client sends `multipart/form-data` and the field name matches:

```python
@app.post("/upload")
async def upload(file: UploadFile = File()):   # field name is "file"
    ...
```

```bash
curl -X POST /upload -F "file=@photo.jpg"
```

---

## Middleware

### CORS preflight fails

Add `CORSMiddleware` before any routes are hit:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourfrontend.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Middleware order matters

Middleware is applied in **reverse registration order**.  Add more-specific middleware
last (it will run first):

```python
app.add_middleware(CORSMiddleware, ...)     # outer (registered first)
app.add_middleware(TimingMiddleware)        # inner (registered last)
```

---

## Dependencies

### `Depends()` result is not cached between calls

By default, `Depends` **is** cached per request.  If you see it called multiple
times, check that you're passing the same callable (not a lambda):

```python
# BAD — new lambda each time, never cached
Depends(lambda: get_db())

# GOOD
Depends(get_db)
```

### Circular dependency

FasterAPI does not detect circular `Depends()` chains.  If you get a `RecursionError`,
look for A → B → A dependency cycles.

---

## Database

### `asyncpg` / SQLAlchemy session errors in tests

Each test must use its own session.  Share a session factory, not a session.

### `RuntimeError: Task attached to a different loop`

Do not share asyncio objects (like connections) between `asyncio.run()` calls.
Use `on_startup` / `on_shutdown` to manage the lifecycle within a single event loop.

---

## Performance

### Throughput is lower than expected

1. Enable uvloop: `pip install uvicorn[standard]` or `pip install faster-api-web[all]`.
2. Use multiple workers: `uvicorn main:app --workers 4`.
3. Profile with `py-spy` or `cProfile` to find bottlenecks.
4. Check if database queries are the bottleneck (add `EXPLAIN ANALYZE`).

### High memory usage

1. Check for memory leaks in background tasks.
2. Ensure database connections are properly released (`async with session`).
3. Profile with `tracemalloc` or `memray`.

---

## OpenAPI / Swagger UI

### Swagger UI is blank or shows errors

1. Visit `/openapi.json` directly and check for JSON syntax errors.
2. Ensure `docs_url` and `openapi_url` are not set to `None`.
3. Check browser console for CORS errors if the UI is hosted separately.

### Response schema is missing or wrong

Make sure the return type annotation is a `msgspec.Struct` or a supported primitive
type.  `dict` return types generate a generic object schema.

---

## WebSockets

### WebSocket connection immediately closes

The handler must `await ws.accept()` before sending or receiving data.

### WebSocket 4004 error

No WebSocket route matched the requested path.  Check path spelling and trailing
slashes.

---

## Getting help

- **GitHub Issues:** [github.com/FasterApiWeb/FasterAPI/issues](https://github.com/FasterApiWeb/FasterAPI/issues)
- **Source code:** Browse [`FasterAPI/`](https://github.com/FasterApiWeb/FasterAPI/tree/master/FasterAPI) on GitHub.
- **Changelog:** See [CHANGELOG](changelog.md) for recent changes.
