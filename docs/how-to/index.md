# How-To Recipes

Short, focused recipes for common patterns.

---

## Return a plain dict without a struct

```python
@app.get("/info")
async def info():
    return {"version": "1.0", "status": "ok"}
```

---

## Add a global prefix to all routes

Use `include_router` with a prefix on all routers:

```python
app.include_router(router, prefix="/api/v1")
```

Or mount a sub-app:

```python
# All routes in 'api_app' are accessible under /api
# (requires ASGI-level mounting)
```

---

## Redirect to another URL

```python
from FasterAPI import RedirectResponse

@app.get("/old")
async def old_route():
    return RedirectResponse(url="/new", status_code=301)
```

---

## Return a file download

```python
from FasterAPI import FileResponse

@app.get("/download/{filename}")
async def download(filename: str):
    return FileResponse(f"files/{filename}", filename=filename)
```

---

## Accept optional JSON body

```python
@app.patch("/items/{item_id}")
async def partial_update(item_id: int, body: ItemPatch | None = None):
    if body is None:
        return {"item_id": item_id, "updated": False}
    return {"item_id": item_id, "name": body.name}
```

---

## Add a request ID to every response

```python
import uuid
from FasterAPI import BaseHTTPMiddleware

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, scope, receive, send):
        request_id = str(uuid.uuid4())

        async def add_header(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, add_header)

app.add_middleware(RequestIDMiddleware)
```

---

## Parse a comma-separated query parameter

```python
@app.get("/items")
async def list_items(ids: str | None = None):
    id_list = [int(x) for x in ids.split(",")] if ids else []
    return {"ids": id_list}
```

```
GET /items?ids=1,2,3
```

---

## Validate an enum field

```python
from enum import Enum

class Category(str, Enum):
    electronics = "electronics"
    clothing = "clothing"
    food = "food"

@app.get("/products")
async def products(category: Category = Category.electronics):
    return {"category": category}
```

---

## Return 204 No Content

```python
@app.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: int) -> None:
    # perform deletion
    pass
```

---

## Health check with database probe

```python
@app.get("/health")
async def health(db = Depends(get_db)):
    try:
        await db.execute("SELECT 1")
        return {"status": "ok", "db": "ok"}
    except Exception as exc:
        raise HTTPException(503, f"DB error: {exc}")
```

---

## Decode a JWT manually without a library

```python
import base64
import json

def decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload without verification — for inspection only."""
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    padded = parts[1] + "=="  # re-pad base64
    decoded = base64.urlsafe_b64decode(padded)
    return json.loads(decoded)
```

---

## Serve a single-page application (SPA)

```python
@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    return FileResponse("static/index.html")
```

---

## Log request and response timing

```python
import time, logging

logger = logging.getLogger(__name__)

class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, scope, receive, send):
        start = time.perf_counter()
        await self.app(scope, receive, send)
        elapsed_ms = (time.perf_counter() - start) * 1000
        path = scope.get("path", "")
        logger.info("%.1f ms  %s", elapsed_ms, path)

app.add_middleware(TimingMiddleware)
```

---

## Next steps

- [Tutorial](../tutorial/index.md) — step-by-step guide.
- [Advanced User Guide](../advanced/index.md) — deeper topics.
- [FAQ](../faq.md) — troubleshooting.
