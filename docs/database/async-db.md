# Async Database Usage

This page covers the patterns and pitfalls of using async databases in a FasterAPI
application — applicable regardless of whether you use SQLAlchemy, Motor, or another
library.

## The request-scoped session pattern

The most common pattern: open a session at the start of a request and close it
at the end, even if the handler raises.

```python
# Works for SQLAlchemy, asyncpg, aiosqlite, etc.
async def get_db():
    session = SessionFactory()
    try:
        yield session
        await session.commit()   # commit on success
    except Exception:
        await session.rollback() # rollback on error
        raise
    finally:
        await session.close()    # always close
```

Use with `Depends`:

```python
@app.get("/items")
async def list_items(db = Depends(get_db)):
    ...
```

## Connection pool lifecycle

Open the pool **once** at startup, close it **once** at shutdown.  Never open a
pool inside a route handler.

```python
import asyncpg
from FasterAPI import Faster

app = Faster()
_pool: asyncpg.Pool | None = None


@app.on_startup
async def startup():
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )


@app.on_shutdown
async def shutdown():
    if _pool:
        await _pool.close()


async def get_conn():
    async with _pool.acquire() as conn:
        yield conn
```

## Avoiding common mistakes

### Never share a session across requests

Each request must have its own session.  A shared session leads to race conditions
and corrupted state.

```python
# BAD — shared session
session = SessionFactory()

@app.get("/items")
async def list_items():
    return await session.execute(...)  # not safe for concurrent requests
```

```python
# GOOD — per-request session via Depends
@app.get("/items")
async def list_items(db = Depends(get_db)):
    return await db.execute(...)
```

### Don't forget `await`

Calling async methods without `await` returns a coroutine, not the result.

```python
# BAD
result = db.execute(select(Item))   # returns coroutine, not rows

# GOOD
result = await db.execute(select(Item))
```

### Handle connection timeouts

```python
import asyncio

async def get_db_with_timeout():
    try:
        async with asyncio.timeout(5):
            async with SessionFactory() as session:
                yield session
    except asyncio.TimeoutError:
        from FasterAPI import HTTPException
        raise HTTPException(503, "Database unavailable")
```

## Read replicas

Route read-heavy queries to a read replica:

```python
_write_pool: asyncpg.Pool | None = None
_read_pool: asyncpg.Pool | None = None


@app.on_startup
async def startup():
    global _write_pool, _read_pool
    _write_pool = await asyncpg.create_pool(WRITE_DATABASE_URL)
    _read_pool  = await asyncpg.create_pool(READ_DATABASE_URL)


async def get_write_conn():
    async with _write_pool.acquire() as conn:
        yield conn


async def get_read_conn():
    async with _read_pool.acquire() as conn:
        yield conn


@app.get("/items")    # read — goes to replica
async def list_items(db = Depends(get_read_conn)):
    return await db.fetch("SELECT * FROM items")


@app.post("/items")   # write — goes to primary
async def create_item(body: ItemCreate, db = Depends(get_write_conn)):
    return await db.fetchrow("INSERT INTO items ...")
```

## Transactions

Wrap multi-step operations in a transaction:

```python
@app.post("/transfer")
async def transfer(from_id: int, to_id: int, amount: float, db = Depends(get_db)):
    async with db.begin():
        await db.execute(
            "UPDATE accounts SET balance = balance - $1 WHERE id = $2",
            amount, from_id,
        )
        await db.execute(
            "UPDATE accounts SET balance = balance + $1 WHERE id = $2",
            amount, to_id,
        )
    return {"transferred": amount}
```

## Health check endpoint

```python
@app.get("/health/db")
async def db_health(db = Depends(get_db)):
    try:
        await db.execute("SELECT 1")
        return {"db": "ok"}
    except Exception as exc:
        raise HTTPException(503, f"Database error: {exc}")
```

## Tuning the pool

| Parameter | Guidance |
|---|---|
| `min_size` | ≥ 1; keep connections warm |
| `max_size` | Match worker count × 2–5; check DB max_connections |
| `max_inactive_connection_lifetime` | Recycle idle connections (e.g. 300s) |
| `command_timeout` | Fail fast on slow queries |

## Next steps

- [SQL with SQLAlchemy](sqlalchemy.md) — ORM-based SQL.
- [NoSQL — MongoDB](nosql-mongodb.md) — document store.
- [Lifespan Events](../advanced/lifespan.md) — startup / shutdown hooks.
