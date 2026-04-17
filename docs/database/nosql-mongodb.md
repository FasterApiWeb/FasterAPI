# NoSQL — MongoDB with Motor

**Motor** is the official async Python driver for MongoDB.  It wraps PyMongo with
asyncio support and integrates naturally with FasterAPI's dependency system.

## Installation

```bash
pip install motor
```

## Connection

```python
# db/mongo.py
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URL = os.environ.get("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGODB_DB", "mydb")

client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    if client is None:
        raise RuntimeError("MongoDB client not initialised")
    return client


def get_database():
    return get_client()[DB_NAME]
```

## Lifespan setup

```python
from FasterAPI import Faster
import db.mongo as mongo

app = Faster()


@app.on_startup
async def connect_mongo():
    mongo.client = AsyncIOMotorClient(mongo.MONGODB_URL)
    # Verify connection
    await mongo.client.admin.command("ping")
    print("MongoDB connected")


@app.on_shutdown
async def disconnect_mongo():
    if mongo.client:
        mongo.client.close()
```

## Collection dependency

```python
from FasterAPI import Depends
from motor.motor_asyncio import AsyncIOMotorCollection


def get_items_collection() -> AsyncIOMotorCollection:
    return mongo.get_database()["items"]
```

## msgspec models

```python
import msgspec
from bson import ObjectId


class ItemCreate(msgspec.Struct):
    name: str
    price: float
    tags: list[str] = []


class Item(msgspec.Struct):
    id: str
    name: str
    price: float
    tags: list[str]
```

## CRUD routes

```python
from FasterAPI import Faster, Depends, HTTPException, Path
from motor.motor_asyncio import AsyncIOMotorCollection

app = Faster()


def _doc_to_item(doc: dict) -> Item:
    return Item(
        id=str(doc["_id"]),
        name=doc["name"],
        price=doc["price"],
        tags=doc.get("tags", []),
    )


@app.get("/items", tags=["items"])
async def list_items(
    col: AsyncIOMotorCollection = Depends(get_items_collection),
):
    docs = await col.find({}).to_list(length=100)
    return [_doc_to_item(d) for d in docs]


@app.post("/items", status_code=201, tags=["items"])
async def create_item(
    body: ItemCreate,
    col: AsyncIOMotorCollection = Depends(get_items_collection),
):
    doc = {"name": body.name, "price": body.price, "tags": body.tags}
    result = await col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_item(doc)


@app.get("/items/{item_id}", tags=["items"])
async def get_item(
    item_id: str = Path(),
    col: AsyncIOMotorCollection = Depends(get_items_collection),
):
    from bson import ObjectId, errors as bson_errors
    try:
        oid = ObjectId(item_id)
    except bson_errors.InvalidId:
        raise HTTPException(status_code=400, detail="Invalid item ID")
    doc = await col.find_one({"_id": oid})
    if doc is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return _doc_to_item(doc)


@app.delete("/items/{item_id}", status_code=204, tags=["items"])
async def delete_item(
    item_id: str = Path(),
    col: AsyncIOMotorCollection = Depends(get_items_collection),
):
    from bson import ObjectId
    result = await col.delete_one({"_id": ObjectId(item_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
```

## Indexes

Create indexes at startup for performance:

```python
@app.on_startup
async def create_indexes():
    col = mongo.get_database()["items"]
    await col.create_index("name")
    await col.create_index([("price", 1)])
    await col.create_index("tags")
```

## Searching and filtering

```python
@app.get("/items/search", tags=["items"])
async def search_items(
    q: str | None = None,
    max_price: float | None = None,
    col: AsyncIOMotorCollection = Depends(get_items_collection),
):
    filters: dict = {}
    if q:
        filters["name"] = {"$regex": q, "$options": "i"}
    if max_price is not None:
        filters["price"] = {"$lte": max_price}
    docs = await col.find(filters).to_list(length=50)
    return [_doc_to_item(d) for d in docs]
```

## Aggregation pipeline

```python
@app.get("/stats", tags=["stats"])
async def item_stats(
    col: AsyncIOMotorCollection = Depends(get_items_collection),
):
    pipeline = [
        {"$group": {"_id": None, "avg_price": {"$avg": "$price"}, "count": {"$sum": 1}}}
    ]
    result = await col.aggregate(pipeline).to_list(length=1)
    return result[0] if result else {"avg_price": 0, "count": 0}
```

## Next steps

- [Async Database Usage](async-db.md) — patterns for connection lifecycle.
- [SQL with SQLAlchemy](sqlalchemy.md) — relational alternative.
