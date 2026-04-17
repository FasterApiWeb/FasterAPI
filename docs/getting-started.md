# Getting Started

Use **Python 3.13** if you can (see [Python 3.13 & compatibility](python-313.md)); the
minimum supported release is **3.10**. Create a **virtual environment** before
installing dependencies.

## Install

```bash
pip install faster-api-web
```

Optional **uvloop** (recommended on Linux for lower event-loop overhead):

```bash
pip install faster-api-web[all]
```

For **`TestClient`** (integration tests), add **httpx**:

```bash
pip install faster-api-web[test]
```

For development (tests, linting, benchmarks):

```bash
pip install faster-api-web[dev]
```

## Minimal application

Create `main.py`:

```python
import msgspec
from FasterAPI import Faster

app = Faster()


class Item(msgspec.Struct):
    name: str
    price: float


@app.get("/items/{item_id}")
async def read_item(item_id: str):
    return {"item_id": item_id}


@app.post("/items")
async def create_item(item: Item):
    return {"received": item}
```

## Run with Uvicorn

```bash
uvicorn main:app --reload
```

You should see:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [...]
INFO:     Started server process [...]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

## Try it with curl

```bash
# GET request
curl http://127.0.0.1:8000/items/42
# {"item_id":"42"}

# POST request with JSON body
curl -X POST http://127.0.0.1:8000/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Widget","price":9.99}'
# {"received":{"name":"Widget","price":9.99}}
```

## Interactive API docs

Open `http://127.0.0.1:8000/docs` for the **Swagger UI** — automatically generated
from your route definitions.

From the Swagger UI you can:

- Browse all endpoints grouped by tags
- Click **Try it out** on any route to send a live request
- See the full request and response schema

Alternative docs are available at `http://127.0.0.1:8000/redoc`.

## Imports at a glance

| What you need | Import |
|---|---|
| Application class | `from FasterAPI import Faster` |
| Router (sub-router) | `from FasterAPI import FasterRouter` |
| Request body helpers | `from FasterAPI import Body, Form, File` |
| URL / query helpers | `from FasterAPI import Path, Query, Header, Cookie` |
| Responses | `from FasterAPI import JSONResponse, HTMLResponse, FileResponse, …` |
| Models | `import msgspec` — use `msgspec.Struct` |
| DI | `from FasterAPI import Depends` |
| Exceptions | `from FasterAPI import HTTPException` |
| Middleware | `from FasterAPI import CORSMiddleware, GZipMiddleware, …` |
| WebSocket | `from FasterAPI import WebSocket, WebSocketDisconnect` |
| Background tasks | `from FasterAPI import BackgroundTasks` |
| Testing | `from FasterAPI import TestClient` |

## Project structure (recommended)

```
myproject/
├── main.py          # app = Faster(), include_router calls
├── routers/
│   ├── items.py     # FasterRouter for items
│   └── users.py     # FasterRouter for users
├── models.py        # msgspec.Struct definitions
├── dependencies.py  # Shared Depends() callables
└── tests/
    ├── conftest.py
    └── test_items.py
```

## Next steps

- Follow the full [Tutorial](tutorial/index.md).
- Start with [Path Parameters](tutorial/path-parameters.md) → [Query Parameters](tutorial/query-parameters.md) → [Request Body](tutorial/request-body.md).
- If you already use FastAPI, read [Migrating from FastAPI](migration-from-fastapi.md).
- For performance context, see the [Benchmarks](benchmarks.md) page.
