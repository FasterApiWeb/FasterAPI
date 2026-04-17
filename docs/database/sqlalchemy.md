# SQL Databases with SQLAlchemy

This guide uses **SQLAlchemy 2** with an **async engine** and **asyncpg** (PostgreSQL)
or **aiosqlite** (SQLite for development/testing).

## Installation

```bash
# PostgreSQL
pip install sqlalchemy asyncpg alembic

# SQLite (dev / testing)
pip install sqlalchemy aiosqlite
```

## Define models

```python
# db/models.py
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, Boolean


class Base(DeclarativeBase):
    pass


class ItemORM(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
```

## Engine and session factory

```python
# db/session.py
import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./dev.db")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```

## Lifespan — create tables at startup

```python
# main.py
from FasterAPI import Faster
from db.session import engine
from db.models import Base

app = Faster()


@app.on_startup
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.on_shutdown
async def close_engine():
    await engine.dispose()
```

## Session dependency

```python
# db/deps.py
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

## msgspec structs for request/response

Keep ORM models separate from API models:

```python
import msgspec


class ItemCreate(msgspec.Struct):
    name: str
    price: float
    in_stock: bool = True


class ItemResponse(msgspec.Struct):
    id: int
    name: str
    price: float
    in_stock: bool
```

## CRUD routes

```python
from FasterAPI import Faster, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.deps import get_db
from db.models import ItemORM

app = Faster()


@app.get("/items", tags=["items"])
async def list_items(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ItemORM))
    items = result.scalars().all()
    return [
        ItemResponse(id=i.id, name=i.name, price=i.price, in_stock=i.in_stock)
        for i in items
    ]


@app.post("/items", status_code=201, tags=["items"])
async def create_item(body: ItemCreate, db: AsyncSession = Depends(get_db)):
    item = ItemORM(name=body.name, price=body.price, in_stock=body.in_stock)
    db.add(item)
    await db.flush()  # populate item.id without committing yet
    return ItemResponse(id=item.id, name=item.name, price=item.price, in_stock=item.in_stock)


@app.get("/items/{item_id}", tags=["items"])
async def get_item(item_id: int = Path(), db: AsyncSession = Depends(get_db)):
    item = await db.get(ItemORM, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return ItemResponse(id=item.id, name=item.name, price=item.price, in_stock=item.in_stock)


@app.delete("/items/{item_id}", status_code=204, tags=["items"])
async def delete_item(item_id: int = Path(), db: AsyncSession = Depends(get_db)):
    item = await db.get(ItemORM, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.delete(item)
```

## Migrations with Alembic

```bash
alembic init alembic
```

Edit `alembic/env.py` to import your models and async engine:

```python
from db.models import Base
from db.session import DATABASE_URL
from sqlalchemy.ext.asyncio import create_async_engine

target_metadata = Base.metadata
```

Create and apply a migration:

```bash
alembic revision --autogenerate -m "create items table"
alembic upgrade head
```

## Testing with SQLite in-memory

```python
# tests/conftest.py
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from db.models import Base

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()
```

## Next steps

- [Async Database Usage](async-db.md) — connection pool patterns.
- [NoSQL — MongoDB](nosql-mongodb.md) — document databases.
