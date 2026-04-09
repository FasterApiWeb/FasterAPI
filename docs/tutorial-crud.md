# Tutorial: build a CRUD app

A small **in-memory** REST API for items. It shows routing, JSON bodies with **msgspec**,
and standard HTTP verbs.

## Complete example

```python
from __future__ import annotations

import msgspec
from FasterAPI import Faster, HTTPException, Path

app = Faster()

# In-memory store (demo only — data is lost when the process exits)
_db: dict[int, "Item"] = {}
_next_id = 1


class ItemCreate(msgspec.Struct):
    name: str
    description: str = ""


class Item(msgspec.Struct):
    id: int
    name: str
    description: str


@app.get("/items")
async def list_items() -> list[Item]:
    return list(_db.values())


@app.get("/items/{item_id}")
async def get_item(item_id: int = Path()) -> Item:
    if item_id not in _db:
        raise HTTPException(status_code=404, detail="Item not found")
    return _db[item_id]


@app.post("/items", status_code=201)
async def create_item(body: ItemCreate) -> Item:
    global _next_id
    item = Item(id=_next_id, name=body.name, description=body.description)
    _db[_next_id] = item
    _next_id += 1
    return item


@app.put("/items/{item_id}")
async def replace_item(item_id: int = Path(), body: ItemCreate | None = None) -> Item:
    if body is None:
        raise HTTPException(status_code=400, detail="Body required")
    if item_id not in _db:
        raise HTTPException(status_code=404, detail="Item not found")
    updated = Item(id=item_id, name=body.name, description=body.description)
    _db[item_id] = updated
    return updated


@app.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: int = Path()) -> None:
    if item_id not in _db:
        raise HTTPException(status_code=404, detail="Not found")
    del _db[item_id]
```

## Run it

```bash
uvicorn main:app --reload
```

Try:

```bash
curl -s localhost:8000/items
curl -s -X POST localhost:8000/items -H 'Content-Type: application/json' \
  -d '{"name":"alpha","description":"first"}'
```

## Ideas to extend

- Swap the dict for a real database and keep handlers thin.
- Add `Depends()` for shared auth or pagination.
- Serve OpenAPI from the same app (default `Faster()` enables docs unless you turn them off).
