# Database Integration

FasterAPI is database-agnostic — use any Python library that works with async I/O.
This section covers the most common choices.

## Pages

| Topic | What you learn |
|---|---|
| [SQL with SQLAlchemy](sqlalchemy.md) | Async SQLAlchemy 2, sessions, models, migrations |
| [NoSQL — MongoDB](nosql-mongodb.md) | Motor (async MongoDB), documents, indices |
| [Async Database Usage](async-db.md) | Pattern guide: sessions, pools, connection lifecycle |

## Choosing a database library

| Use case | Recommended |
|---|---|
| PostgreSQL / MySQL / SQLite | SQLAlchemy 2 (async) |
| PostgreSQL (lightweight) | `asyncpg` directly |
| MongoDB | Motor |
| Redis (cache/queue) | `redis-py` (async) |
| Key-value / embedded | `aiosqlite` for SQLite |

## General pattern

1. **Open a pool / session factory at startup** (see [Lifespan Events](../advanced/lifespan.md)).
2. **Inject a session per request** using `Depends()`.
3. **Close the session after the response** (use `try/finally` in the dependency).
4. **Close the pool at shutdown**.

```python
# Generic pattern sketch
@app.on_startup
async def startup():
    app_state.pool = await create_pool(DATABASE_URL)

@app.on_shutdown
async def shutdown():
    await app_state.pool.close()

async def get_session():
    async with app_state.pool.acquire() as conn:
        yield conn

@app.get("/items")
async def list_items(db = Depends(get_session)):
    return await db.fetch("SELECT * FROM items")
```

## Environment variables

Store the connection string in `DATABASE_URL`:

```bash
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/mydb

# SQLite (development)
DATABASE_URL=sqlite+aiosqlite:///./dev.db

# MongoDB
MONGODB_URL=mongodb://localhost:27017
```

## Next steps

- [Settings & Environment Variables](../advanced/settings.md) — managing `DATABASE_URL`.
- [Lifespan Events](../advanced/lifespan.md) — startup / shutdown hooks for pools.
