"""Minimal FasterAPI example — hello world with common patterns.

Run:
    python examples/basic_app.py

Then visit:
    http://localhost:8000/docs   — Swagger UI
    http://localhost:8000/       — Hello world
    http://localhost:8000/greet/Alice?greeting=Hi  — Path + query params
"""

import msgspec

from FasterAPI import Faster, Path, Query

app = Faster(title="Basic App", version="1.0.0", description="A minimal FasterAPI example")


# ── GET with path parameter ──

@app.get("/greet/{name}", tags=["greetings"], summary="Greet a user by name")
async def greet(name: str = Path(), greeting: str = Query("Hello")):
    """Returns a personalised greeting. Use ?greeting= to customise."""
    return {"message": f"{greeting}, {name}!"}


# ── POST with msgspec Struct body ──

class Item(msgspec.Struct):
    """A simple item with a name and price."""
    name: str
    price: float
    in_stock: bool = True


@app.post("/items", tags=["items"], summary="Create an item", status_code=201)
async def create_item(item: Item):
    """Accepts a JSON body validated against the Item schema."""
    return {"id": 1, "name": item.name, "price": item.price, "in_stock": item.in_stock}


# ── GET with query parameters ──

@app.get("/search", tags=["items"], summary="Search items")
async def search(q: str = Query(""), skip: str = Query("0"), limit: str = Query("10")):
    """Search items by keyword with pagination."""
    return {"query": q, "skip": int(skip), "limit": int(limit), "results": []}


# ── Root ──

@app.get("/", summary="Root")
async def root():
    return {"message": "Hello, FasterAPI!", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
