# Lifespan Events

Lifespan events let you run code **once at startup** and **once at shutdown** — ideal
for opening database connections, warming caches, or releasing resources cleanly.

## `on_startup` and `on_shutdown`

```python
from FasterAPI import Faster

app = Faster()

_db_pool = None


@app.on_startup
async def startup():
    global _db_pool
    # e.g. open an async DB connection pool
    _db_pool = await open_pool()
    print("Database connected")


@app.on_shutdown
async def shutdown():
    if _db_pool:
        await _db_pool.close()
    print("Database disconnected")
```

## Synchronous handlers

Both async and sync callables are supported:

```python
@app.on_startup
def load_ml_model():
    global model
    import joblib
    model = joblib.load("model.pkl")
    print("Model loaded")
```

## Multiple handlers

Register as many as you need — they run in registration order:

```python
@app.on_startup
async def connect_db(): ...

@app.on_startup
async def connect_redis(): ...

@app.on_startup
def warm_cache(): ...
```

## Sharing state between handlers and routes

Use module-level variables or a dedicated state object:

```python
class AppState:
    db: object = None
    cache: dict = {}

state = AppState()


@app.on_startup
async def init_db():
    state.db = await create_connection()


@app.get("/items")
async def list_items():
    rows = await state.db.fetch("SELECT * FROM items")
    return rows
```

## Startup validation

Fail fast if required configuration is missing:

```python
import os, sys

@app.on_startup
def validate_config():
    required = ["DATABASE_URL", "SECRET_KEY"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"Missing env vars: {missing}", file=sys.stderr)
        raise RuntimeError(f"Missing required configuration: {missing}")
```

If a startup handler raises, the ASGI server receives `lifespan.startup.failed` and
terminates the process — preventing a misconfigured app from accepting requests.

## Using lifespan with ASGI servers

FasterAPI handles the `lifespan` ASGI scope natively. Pass `--lifespan on` to
uvicorn (the default):

```bash
uvicorn main:app --lifespan on
```

## Contextlib pattern (future-compatible)

For testing or frameworks that prefer a context manager, you can wrap the handlers:

```python
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan():
    # startup
    state.db = await create_connection()
    yield
    # shutdown
    await state.db.close()


# FasterAPI 's on_startup / on_shutdown approach covers the same ground
```

## Next steps

- [Settings & Environment Variables](settings.md) — validate config at startup.
- [Database Integration](../database/index.md) — connection pools and sessions.
