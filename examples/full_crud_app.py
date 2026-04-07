"""Full CRUD application example with dependency injection."""

import msgspec

from FasterAPI.app import Faster
from FasterAPI.dependencies import Depends
from FasterAPI.exceptions import HTTPException
from FasterAPI.params import Path, Query

app = Faster(title="CRUD App", version="1.0.0")

# --- Models ---


class ItemCreate(msgspec.Struct):
    name: str
    price: float
    in_stock: bool = True


class ItemUpdate(msgspec.Struct):
    name: str | None = None
    price: float | None = None
    in_stock: bool | None = None


# --- In-memory store ---

_db: dict[str, dict] = {}
_counter = 0


# --- Dependencies ---


async def get_db():
    return _db


# --- Routes ---


@app.get("/items", tags=["items"], summary="List items")
async def list_items(
    skip: int = Query(0),
    limit: int = Query(10),
    db: dict = Depends(get_db),
):
    items = list(db.values())
    return items[skip : skip + limit]


@app.post("/items", tags=["items"], summary="Create item", status_code=201)
async def create_item(item: ItemCreate, db: dict = Depends(get_db)):
    global _counter
    _counter += 1
    item_id = str(_counter)
    record = {"id": item_id, "name": item.name, "price": item.price, "in_stock": item.in_stock}
    db[item_id] = record
    return record


@app.get("/items/{item_id}", tags=["items"], summary="Get item", response_model=ItemCreate)
async def get_item(item_id: str = Path(), db: dict = Depends(get_db)):
    if item_id not in db:
        raise HTTPException(status_code=404, detail="Item not found")
    return db[item_id]


@app.put("/items/{item_id}", tags=["items"], summary="Update item")
async def update_item(
    item: ItemUpdate,
    item_id: str = Path(),
    db: dict = Depends(get_db),
):
    if item_id not in db:
        raise HTTPException(status_code=404, detail="Item not found")
    record = db[item_id]
    if item.name is not None:
        record["name"] = item.name
    if item.price is not None:
        record["price"] = item.price
    if item.in_stock is not None:
        record["in_stock"] = item.in_stock
    return record


@app.delete("/items/{item_id}", tags=["items"], summary="Delete item", status_code=204)
async def delete_item(item_id: str = Path(), db: dict = Depends(get_db)):
    if item_id not in db:
        raise HTTPException(status_code=404, detail="Item not found")
    del db[item_id]
    return None


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
